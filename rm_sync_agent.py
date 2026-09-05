r"""rm_sync_agent.py — RM_SYNC_AGENT: jedyny łącznik między RM_BAZA a portalem RM_RFQ.

DLACZEGO ISTNIEJE
-----------------
Portal RM_RFQ stoi na serwerze wystawionym do internetu (kooperanci wchodzą
magic-linkami z maila). RM_BAZA i dyski z rysunkami (V:\, Y:\) są w sieci
firmowej i NIE MOGĄ być z internetu osiągalne. Gdyby portal sam sięgał po
master.sqlite albo pliki z V:\, to znaczyłoby, że proces dostępny z zewnątrz ma
ścieżkę do wnętrza sieci — tego unikamy.

Dlatego cały ruch przechodzi przez tego agenta:
  - agent działa W SIECI FIRMOWEJ (ma lokalny dostęp do master.sqlite i V:\),
  - agent SAM inicjuje wszystkie połączenia do portalu (wychodzące HTTPS),
  - portal nie zna ani nie potrzebuje żadnej ścieżki do zasobów firmowych.

    SIEĆ FIRMOWA                                  SERWER PORTALU (internet)
    ┌──────────────────────────┐                  ┌────────────────────┐
    │ master.sqlite   V:\ Y:\  │                  │  RM_RFQ (Flask)    │
    │        ▲          ▲      │                  │  rm_rfq.db         │
    │        └────┬─────┘      │   HTTPS (out)    │        ▲           │
    │      RM_SYNC_AGENT ──────┼─────────────────►│  API + X-API-Key   │
    └──────────────────────────┘                  └────────────────────┘

TRZY KANAŁY
-----------
1. Kooperanci   RM_BAZA → portal : czyta suppliers z master.sqlite, POST /api/suppliers/sync
2. Rysunki      RM_BAZA → portal : czyta plik z dysku, POST /api/rfq/<id>/items (multipart)
3. Wyniki       portal → RM_BAZA : GET /api/sync/changes?after_id=N, zapis do master.sqlite

Kanały 1 i 3 uruchamiane cyklicznie (Task Scheduler, np. co 60 s):
    python rm_sync_agent.py --once
Kanał 2 wywoływany z GUI RM_BAZA po zaznaczeniu rysunków:
    from rm_sync_agent import RMSyncAgent
    RMSyncAgent().push_drawing(rfq_id, drawing_number, [r'V:\...\rys.pdf'])

KONFIGURACJA
------------
Wszystko w master.sqlite → tabela settings (klucz/wartość):
    rfq_portal_url   — np. https://oferty.rmpak.pl
    rfq_api_key      — ten sam klucz co RM_RFQ/config.json → rm_baza_api_key
    rfq_last_sync_id — kursor kanału 3, agent aktualizuje go sam
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import requests

MASTER_DB_DEFAULT = r'Y:\RM_BAZA\master.sqlite'
HTTP_TIMEOUT = 30

# Nazwy kolumn w RM_BAZA.suppliers bywają różne między instalacjami (schemat
# ewoluował). Mapowanie jest TUTAJ, nie w portalu — portal dostaje już
# znormalizowany JSON i nie musi nic wiedzieć o schemacie RM_BAZA.
SUPPLIER_COLUMN_ALIASES = {
    'name': ['name', 'nazwa', 'supplier_name'],
    'email': ['email', 'email_default'],
    'phone': ['phone', 'phone_default'],
    'contact_person': ['contact', 'contact_info'],
    'nip': ['nip'],
    'active': ['is_active', 'active', 'enabled'],
}


def _pick_column(available: set, aliases: list) -> str | None:
    for name in aliases:
        if name in available:
            return name
    return None


class RMSyncAgent:
    def __init__(self, master_path: str = MASTER_DB_DEFAULT):
        self.master_path = master_path
        self.portal_url = self._portal_url_for_machine()
        self.api_key = self._setting('rfq_api_key', '')
        if not self.portal_url or not self.api_key:
            raise RuntimeError(
                'Brak konfiguracji w master.sqlite → settings: '
                'ustaw rfq_portal_url i rfq_api_key'
            )

    # --- dostęp do master.sqlite -------------------------------------------

    def _open_master(self, readonly: bool = True) -> sqlite3.Connection:
        uri = Path(self.master_path).as_posix()
        if readonly:
            # Ścieżki UNC (\\nic\... -> //nic/...) w SQLite URI: "file://nic/..."
            # traktuje "nic" jako authority hosta i odrzuca. Poprawny zapis to
            # pusta authority: file:////nic/... (4 ukośniki). Ten sam fix co
            # auth.py/db.py — pozwala agentowi czytać przez UNC na serwerze
            # (Task Scheduler mapuje \\nic bez litery dysku).
            if uri.startswith('//'):
                file_uri = 'file:////' + uri.lstrip('/')
            else:
                file_uri = f'file:{uri}'
            con = sqlite3.connect(f'{file_uri}?mode=ro', uri=True, timeout=10)
        else:
            con = sqlite3.connect(self.master_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    # Nazwy maszyn serwerowych — te same co SERVER_HOSTNAMES w RM_BAZA
    # i server_hostnames w config.json aplikacji webowych.
    SERVER_HOSTNAMES = ('W2019S', 'SERWER')

    def _portal_url_for_machine(self) -> str:
        """Adres portalu dla TEJ maszyny.

        W domu portal stoi na localhost, w firmie na serwerze — a master.sqlite
        jest wspólny, więc jeden adres nie wystarcza. Kolejność:

          1. settings['rfq_portal_url_server'] / '..._local' — jeśli ustawione,
          2. settings['rfq_portal_url'] — wspólny/starszy klucz (zgodność wstecz).

        Bez tego agent uruchomiony w firmie próbowałby gadać z domowym
        localhostem i cicho nic by nie synchronizował."""
        import socket as _socket
        try:
            host = _socket.gethostname().upper()
            serwer = any(h in host for h in self.SERVER_HOSTNAMES)
        except Exception:
            serwer = False
        specyficzny = self._setting(
            'rfq_portal_url_server' if serwer else 'rfq_portal_url_local', '')
        return (specyficzny or self._setting('rfq_portal_url', '')).rstrip('/')

    def _setting(self, key: str, default: str = '') -> str:
        con = self._open_master()
        try:
            row = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return row['value'] if row and row['value'] is not None else default
        finally:
            con.close()

    def _set_setting(self, key: str, value: str) -> None:
        con = self._open_master(readonly=False)
        try:
            con.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now','localtime')) "
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at',
                (key, value)
            )
            con.commit()
        finally:
            con.close()

    # --- HTTP ---------------------------------------------------------------

    def _headers(self) -> dict:
        return {'X-API-Key': self.api_key}

    # --- Kanał 1: kooperanci → portal --------------------------------------

    def push_suppliers(self) -> int:
        """Czyta suppliers z master.sqlite i wypycha pełną listę do portalu.
        Portal robi upsert po supplier_id, więc nie musimy śledzić zmian."""
        con = self._open_master()
        try:
            cols = {r[1] for r in con.execute('PRAGMA table_info(suppliers)')}
            if not cols:
                raise RuntimeError('Tabela suppliers nie istnieje w master.sqlite')
            col_map = {k: _pick_column(cols, aliases) for k, aliases in SUPPLIER_COLUMN_ALIASES.items()}
            if not col_map['name']:
                raise RuntimeError('Nie znaleziono kolumny z nazwą firmy w suppliers')

            select_cols = ['supplier_id'] + [c for c in col_map.values() if c]
            rows = con.execute(f'SELECT {", ".join(select_cols)} FROM suppliers').fetchall()

            # Tagi kooperantów: słownik + przypisania (RM_BAZA jest właścicielem;
            # portal RM_RFQ tylko czyta kopię). Puste, gdy tabele jeszcze nie
            # istnieją (starsza baza) — sync suppliers ma działać niezależnie.
            tags_dict, tag_ids_by_supplier = [], {}
            try:
                tag_rows = con.execute(
                    'SELECT id, name, label, sort_order FROM rfq_tags ORDER BY sort_order, label'
                ).fetchall()
                tags_dict = [dict(r) for r in tag_rows]
                for r in con.execute('SELECT supplier_id, tag_id FROM rfq_supplier_tags'):
                    tag_ids_by_supplier.setdefault(r['supplier_id'], []).append(r['tag_id'])
            except Exception:
                pass
        finally:
            con.close()

        suppliers = []
        for row in rows:
            values = dict(row)
            sid = values['supplier_id']
            suppliers.append({
                'supplier_id': sid,
                'name': values.get(col_map['name']) or '',
                'email': values.get(col_map['email']) if col_map['email'] else None,
                'phone': values.get(col_map['phone']) if col_map['phone'] else None,
                'contact_person': values.get(col_map['contact_person']) if col_map['contact_person'] else None,
                'nip': values.get(col_map['nip']) if col_map['nip'] else None,
                'active': 1 if (values.get(col_map['active']) if col_map['active'] else 1) else 0,
                'tag_ids': tag_ids_by_supplier.get(sid, []),
            })

        resp = requests.post(
            f'{self.portal_url}/api/suppliers/sync',
            headers=self._headers(),
            json={'suppliers': suppliers, 'tags': tags_dict}, timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json().get('saved', 0)

    # --- Kanał 2: rysunki → portal -----------------------------------------

    def list_rfqs(self, only_active: bool = True) -> list[dict]:
        """Lista RFQ z portalu — do okna wyboru "wyślij do którego zapytania"."""
        resp = requests.get(
            f'{self.portal_url}/api/rfq/list',
            headers=self._headers(),
            params={} if only_active else {'all': '1'},
            timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def list_rfq_drawings(self, rfq_id: int) -> list[str]:
        """Numery rysunków już w danym RFQ — RM_BAZA sprawdza przed wysyłką,
        żeby ostrzec przed dublem (ta sama pozycja drugi raz)."""
        resp = requests.get(
            f'{self.portal_url}/api/rfq/{rfq_id}/drawings',
            headers=self._headers(), timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json().get('drawings', [])

    @staticmethod
    def _contact_fields(contact: dict | None) -> dict:
        """Dane osoby prowadzącej zapytanie → pola contact_* dla portalu.

        Kooperant dostawał zapytanie „od RMPAK", bez nazwiska — przy pytaniu
        technicznym musiał szukać kontaktu sam. Portal pokazuje te dane nad
        listą pozycji i w stopce maila.

        `contact` przychodzi z RM_BAZA (employees w RM_MANAGER, po loginie
        zalogowanego). Pusty dict/None → nie wysyłamy nic i portal ZOSTAWIA
        zapisany kontakt bez zmian (nie kasuje go).
        """
        if not contact:
            return {}
        out = {}
        for src, dst in (('login', 'contact_login'), ('name', 'contact_name'),
                         ('email', 'contact_email'), ('phone', 'contact_phone')):
            val = (contact.get(src) or '').strip()
            if val:
                out[dst] = val
        return out

    def create_rfq(self, title: str, project_number: str | None = None,
                   offer_start_date: str | None = None,
                   offer_deadline: str | None = None,
                   contact: dict | None = None) -> dict:
        """Zakłada nowe RFQ w portalu. Zwraca {rfq_id, code, title}.

        contact — patrz _contact_fields()."""
        payload = {'title': title}
        payload.update(self._contact_fields(contact))
        if project_number:
            payload['project_number'] = project_number
        if offer_start_date:
            payload['offer_start_date'] = offer_start_date
        if offer_deadline:
            payload['offer_deadline'] = offer_deadline
        resp = requests.post(
            f'{self.portal_url}/api/rfq',
            headers=self._headers(), json=payload, timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    # ── ZAMÓWIENIA (ZD z Subiekta) ─────────────────────────────────────────
    #
    # Ten sam kanał co rysunki RFQ: agent czyta pliki w sieci firmowej
    # i wysyła ich zawartość, portal nie zna żadnej ścieżki do V:\ ani Y:\.
    # Różnica jest po stronie portalu — zamówienie pokazuje się dostawcy
    # w widoku TYLKO DO ODCZYTU, bez pól wyceny.
    #
    # ⚠️ KOLEJNOŚĆ MA ZNACZENIE: create_order → push_order_item (pliki) →
    # order_link. Link powstaje NA KOŃCU, żeby nigdy nie trafił do maila
    # adres do zamówienia bez rysunków. `sent_at` w portalu stempluje się
    # dopiero przy generowaniu linku, więc zakładka Subiekt nie pokaże
    # „wysłane" dla czegoś, co nie zdążyło się wysłać.

    def create_order(self, code: str, title: str | None = None,
                     project_number: str | None = None,
                     supplier_name: str | None = None,
                     intro_note: str | None = None,
                     contact: dict | None = None) -> dict:
        """Zakłada (albo aktualizuje) zamówienie w portalu. Zwraca
        {order_id, code, title, created}.

        `code` to numer ZD i jest unikalny — ponowna wysyłka tego samego ZD
        aktualizuje istniejące zamówienie zamiast tworzyć duplikat."""
        payload = {'code': code, 'title': title or code}
        payload.update(self._contact_fields(contact))
        if project_number:
            payload['project_number'] = project_number
        if supplier_name:
            payload['supplier_name'] = supplier_name
        if intro_note:
            payload['intro_note'] = intro_note
        resp = requests.post(f'{self.portal_url}/api/orders',
                             headers=self._headers(), json=payload,
                             timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def push_order_item(self, order_id: int, drawing_number: str,
                        file_paths: list[str] | None = None,
                        name: str | None = None, quantity: float = 1,
                        unit: str = 'szt', material: str | None = None,
                        notes: str | None = None,
                        is_catalog: bool = False) -> dict:
        """Pozycja zamówienia wraz z rysunkami. Pliki opcjonalne — elementy
        handlowe (łożysko, siłownik) nie mają dokumentacji i to jest norma."""
        data = {'drawing_number': drawing_number, 'quantity': str(quantity),
                'unit': unit}
        if name:
            data['name'] = name
        if material:
            data['material'] = material
        if notes:
            data['notes'] = notes
        if is_catalog:
            data['is_catalog'] = 'true'

        files = []
        for path in (file_paths or []):
            files.append(('files', (Path(path).name, Path(path).read_bytes())))

        resp = requests.post(f'{self.portal_url}/api/orders/{order_id}/items',
                             headers=self._headers(), data=data, files=files,
                             timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def order_link(self, order_id: int, supplier_id: int | None = None,
                   nip: str | None = None, email: str | None = None,
                   name: str | None = None) -> dict:
        """Magic-link dla dostawcy — ten adres wkleja się do maila.

        Dostawcę wskazujemy przez supplier_id, NIP albo e-mail. Portal używa
        tego samego tokenu co RFQ, więc dostawca nie zbiera osobnych linków
        do każdego modułu. Gdy nie ma ważnego tokenu, portal zwraca 409 —
        token generuje się w panelu, świadomie, a nie automatem z agenta."""
        payload = {}
        if supplier_id:
            payload['supplier_id'] = supplier_id
        if nip:
            payload['nip'] = nip
        if name:
            payload['name'] = name
        if email:
            payload['email'] = email
        resp = requests.post(f'{self.portal_url}/api/orders/{order_id}/link',
                             headers=self._headers(), json=payload,
                             timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def set_rfq_intro_note(self, rfq_id: int, text: str,
                           mode: str = 'append',
                           contact: dict | None = None) -> dict:
        """Ustawia wspólną informację widoczną dla kooperantów nad listą pozycji.

        mode='append' (domyślnie) DOPISUJE do już istniejącej treści — do
        jednego RFQ wysyła się partiami i nadpisywanie kasowałoby tekst
        z poprzedniej wysyłki. mode='replace' podmienia całość."""
        resp = requests.post(
            f'{self.portal_url}/api/rfq/{rfq_id}/intro-note',
            headers=self._headers(),
            json={'intro_note': text, 'mode': mode, **self._contact_fields(contact)},
            timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def push_drawing(self, rfq_id: int, drawing_number: str, file_paths: list[str],
                     name: str | None = None, quantity: int = 1,
                     material: str | None = None, notes: str | None = None,
                     replace_snapshot: bool = False,
                     contact: dict | None = None) -> dict:
        """Wysyła rysunek jako pozycję RFQ. Agent CZYTA pliki lokalnie i wysyła
        ich zawartość — portal nigdy nie dostaje ścieżki ani dostępu do dysku
        firmowego. Wywoływane z GUI RM_BAZA.

        replace_snapshot=True → file_paths to PEŁNY aktualny komplet plików tej
        pozycji na V:\\; portal zastąpi cały dotychczasowy komplet (usunie typy,
        których tu nie ma) i ostempluje files_updated_at. Używane przy
        „Aktualizuj w RFQ" po wykryciu zmiany rysunku. Odciski (fingerprinty)
        zapisujemy DOPIERO po OK serwera — patrz koniec metody."""
        missing = [p for p in file_paths if not Path(p).is_file()]
        if missing:
            raise FileNotFoundError(f'Nie znaleziono plików: {", ".join(missing)}')

        data = {'drawing_number': drawing_number, 'quantity': str(quantity)}
        if name:
            data['name'] = name
        if material:
            data['material'] = material
        if notes:
            data['notes'] = notes
        if replace_snapshot:
            data['replace_snapshot'] = 'true'
        # Kontakt idzie z KAŻDĄ wysyłką i aktualizacją — portal odświeża snapshot,
        # więc pokazuje osobę, która ostatnio prowadzi sprawę (patrz schema.sql).
        data.update(self._contact_fields(contact))

        # Wczytujemy bajty RAZ: idą do POST i przy okazji liczymy sha1 + zbieramy
        # stat (size/mtime_ns). Zero dodatkowego I/O względem samej wysyłki — te
        # bajty i tak trzeba przeczytać. Odciski trafiają do rfq_pushed_files
        # (lokalnie, master.sqlite), żeby RM_BAZA mógł potem TANIO wykryć, że plik
        # źródłowy na V:\ zmienił się po wysłaniu (kooperant ma zamrożoną kopię).
        # mtime_ns (nie int(mtime)) — pełna rozdzielczość, mniej trafień do
        # drogiej ścieżki hash z powodu zaokrągleń.
        files = []
        fingerprints = []   # (filename, size, mtime_ns, sha1)
        for path in file_paths:
            # stabilny odczyt: stat → read → stat. Jeśli size/mtime drgnęły w
            # trakcie (plik właśnie zapisywany, np. przez Inventora), bajty mogą
            # być częściowe — bierzemy stat SPRZED odczytu tylko gdy plik był
            # spójny, inaczej ufamy stanowi PO odczycie (zgodny z przeczytanymi
            # bajtami). Wysyłamy i tak to, co przeczytaliśmy — user świadomie
            # kliknął wyślij; odcisk ma tylko wiernie opisywać wysłane bajty.
            st1 = os.stat(path)
            raw = Path(path).read_bytes()
            st2 = os.stat(path)
            st = st2 if (st1.st_size != st2.st_size or st1.st_mtime_ns != st2.st_mtime_ns) else st1
            files.append(('files', (Path(path).name, raw)))
            fingerprints.append((Path(path).name, st.st_size,
                                 st.st_mtime_ns, hashlib.sha1(raw).hexdigest()))

        resp = requests.post(
            f'{self.portal_url}/api/rfq/{rfq_id}/items',
            headers=self._headers(), data=data, files=files, timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        result = resp.json()

        # Zapis odcisków (fingerprintów) DOPIERO gdy serwer POTWIERDZIŁ pełny
        # sukces. Przy replace_snapshot portal robi podmianę tylko gdy WSZYSTKIE
        # pliki zapisały się bez błędu (files_replaced=True, brak errors) — jeśli
        # errors niepuste, snapshot NIE został podmieniony, więc odcisków NIE
        # zapisujemy: ⚠ RYS ZMIENIONY ma zostać, bo kooperant dalej ma starą
        # wersję. Dla zwykłej wysyłki (bez replace) zachowujemy się jak dotąd.
        srv_errors = result.get('errors') if isinstance(result, dict) else None
        replace_ok = (not replace_snapshot) or (
            isinstance(result, dict) and result.get('files_replaced') and not srv_errors)
        if replace_ok:
            try:
                self._store_pushed_fingerprints(rfq_id, drawing_number, file_paths, fingerprints)
            except Exception as e:
                print(f'push_drawing: nie zapisano odciskow plikow ({drawing_number}): {e}',
                      file=sys.stderr)
        return result

    @staticmethod
    def _ensure_pushed_files_table(con: sqlite3.Connection) -> None:
        """Odciski plików wysłanych do RFQ — do wykrywania, że źródło na V:\\
        zmieniło się po wysłaniu. Jedna para (rfq_id, path) = jeden wiersz;
        ponowna wysyłka tego samego pliku NADPISUJE odcisk (INSERT OR REPLACE)."""
        con.execute('''
            CREATE TABLE IF NOT EXISTS rfq_pushed_files (
                rfq_id          INTEGER NOT NULL,
                drawing_number  TEXT    NOT NULL,
                path            TEXT    NOT NULL,   -- ścieżka źródłowa na V:\\/bibliotece
                filename        TEXT    NOT NULL,
                size            INTEGER,
                mtime_ns        INTEGER,            -- st_mtime_ns źródła w chwili wysyłki
                sha1            TEXT,               -- sha1 zawartości wysłanej do portalu
                pushed_at       TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (rfq_id, path)
            )
        ''')
        # migracja starych baz (kolumna mtime INTEGER → mtime_ns): dodaj kolumnę
        # jeśli brak. Starych wartości nie konwertujemy — przy pierwszym
        # sprawdzeniu mtime_ns=NULL wymusi hash (bezpiecznie), a udane 'ok'
        # zaktualizuje mtime_ns do bieżącej wartości.
        cols = {r[1] for r in con.execute('PRAGMA table_info(rfq_pushed_files)')}
        if 'mtime_ns' not in cols:
            con.execute('ALTER TABLE rfq_pushed_files ADD COLUMN mtime_ns INTEGER')
        con.execute('CREATE INDEX IF NOT EXISTS idx_rfq_pushed_drawing '
                    'ON rfq_pushed_files(rfq_id, drawing_number)')

    def _store_pushed_fingerprints(self, rfq_id: int, drawing_number: str,
                                   file_paths: list[str], fingerprints: list) -> None:
        con = self._open_master(readonly=False)
        try:
            self._ensure_pushed_files_table(con)
            # Odciski dla tej pozycji zastępujemy w całości: jeśli user wyśle ją
            # ponownie z innym zestawem plików, stare (odpięte) pliki nie mają
            # już wisieć jako "zmienione".
            con.execute('DELETE FROM rfq_pushed_files WHERE rfq_id=? AND drawing_number=?',
                        (rfq_id, drawing_number))
            con.executemany(
                'INSERT OR REPLACE INTO rfq_pushed_files '
                '(rfq_id, drawing_number, path, filename, size, mtime_ns, sha1) '
                'VALUES (?,?,?,?,?,?,?)',
                [(rfq_id, drawing_number, str(path), fn, size, mtime_ns, sha1)
                 for path, (fn, size, mtime_ns, sha1) in zip(file_paths, fingerprints)]
            )
            con.commit()
        finally:
            con.close()

    def notify_doc_update(self, rfq_id: int, drawing_numbers: list[str]) -> dict:
        """Prosi portal o wysyłkę maili „zaktualizowano dokumentację" do
        kooperantów przypisanych do wskazanych pozycji (którzy dostali już
        zaproszenie). Wołane po „Aktualizuj w RFQ", gdy user zgodzi się na mail.
        Zwraca {sent:[nazwy], errors:[...], notified:N}."""
        resp = requests.post(
            f'{self.portal_url}/api/rfq/{rfq_id}/notify-doc-update',
            headers=self._headers(), json={'drawing_numbers': drawing_numbers},
            timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()

    def all_stale_drawings(self) -> list[dict]:
        """WSZYSTKIE pozycje niezgodne ze stanem na dysku, po wszystkich RFQ,
        które mają zapisane odciski. Do panelu „Do pilnowania" w RM_BAZA.

        Zwraca listę {rfq_id, drawing_number, status, changed_files,
        missing_files} tylko dla status in ('changed','missing'). Robi lokalne
        I/O (per plik stat, ewent. hash) — wołać w wątku, nie blokować GUI."""
        con = self._open_master(readonly=False)
        try:
            self._ensure_pushed_files_table(con)
            rfq_ids = [r['rfq_id'] for r in con.execute(
                'SELECT DISTINCT rfq_id FROM rfq_pushed_files').fetchall()]
        finally:
            con.close()

        out = []
        for rfq_id in rfq_ids:
            try:
                fresh = self.check_drawing_freshness(rfq_id) or {}
            except Exception:
                continue
            for dn, info in fresh.items():
                if isinstance(info, dict) and info.get('status') in ('changed', 'missing'):
                    out.append({
                        'rfq_id': rfq_id,
                        'drawing_number': dn,
                        'status': info.get('status'),
                        'changed_files': info.get('changed_files') or [],
                        'missing_files': info.get('missing_files') or [],
                    })
        return out

    def all_docs_to_notify(self) -> list[dict]:
        """WSZYSTKIE pozycje z ZALEGŁYM powiadomieniem o aktualizacji
        dokumentacji: dokumentację podmieniono (files_updated_at), ale nie
        powiadomiono jeszcze o tej wersji (docs_notified_at brak lub starsze).

        Czyta z rfq_results w master.sqlite (dane z portalu, bez SMB I/O — szybko).
        Zwraca [{rfq_id, drawing_number, item_name, rfq_code, files_updated_at}].
        Do tabelki „Do powiadomienia" w RM_BAZA."""
        con = self._open_master(readonly=True)
        try:
            cols = {r[1] for r in con.execute('PRAGMA table_info(rfq_results)')}
            if 'files_updated_at' not in cols or 'docs_notified_at' not in cols:
                return []          # stara baza sprzed migracji — nic do pokazania
            rows = con.execute('''
                SELECT rfq_id, drawing_number, item_name, rfq_code, files_updated_at
                  FROM rfq_results
                 WHERE files_updated_at IS NOT NULL
                   AND (docs_notified_at IS NULL OR docs_notified_at < files_updated_at)
                 ORDER BY rfq_code, drawing_number
            ''').fetchall()
            out = [dict(r) for r in rows]

            # Nazwa detalu: portal często NIE ma jej w rfq_items.name (jest tylko
            # sklejana z nazwy pliku), więc item_name z bazy bywa NULL. Wyciągamy
            # ją z nazwy WYSŁANEGO pliku (rfq_pushed_files) — te dane są lokalnie,
            # zero dodatkowego I/O. Format pliku: "<numer rysunku> <nazwa>.<ext>".
            self._ensure_pushed_files_table(con)
            for d in out:
                if d.get('item_name'):
                    continue
                d['item_name'] = self._name_from_pushed_files(
                    con, d['rfq_id'], d['drawing_number']) or None
            return out
        finally:
            con.close()

    @staticmethod
    def _name_from_pushed_files(con, rfq_id, drawing_number) -> str:
        """Wydłubuje nazwę detalu z nazwy wysłanego pliku (rfq_pushed_files).
        Preferuje PDF/DWF (czysta nazwa bez dopisków typu ", 304 gr8mm" na DXF).
        Zwraca '' gdy nie da się wyznaczyć."""
        rows = con.execute(
            'SELECT filename FROM rfq_pushed_files WHERE rfq_id=? AND drawing_number=?',
            (rfq_id, drawing_number)
        ).fetchall()
        if not rows:
            return ''
        names = [r['filename'] for r in rows if r['filename']]
        # PDF/DWF mają nazwę bez technicznych dopisków — wybierz je najpierw
        preferred = [n for n in names if n.lower().rsplit('.', 1)[-1] in ('pdf', 'dwf')]
        cand = (preferred or names)[0]
        stem = cand.rsplit('.', 1)[0]                      # bez rozszerzenia
        # zdejmij numer rysunku z początku (dokładnie ten drawing_number)
        if stem.startswith(drawing_number):
            stem = stem[len(drawing_number):]
        return stem.strip(' -_,')

    def pushed_paths(self, rfq_id: int, drawing_number: str) -> list[str]:
        """Ścieżki plików wysłanych ostatnio dla tej pozycji (z odcisków).
        Do „Aktualizuj w RFQ": wyznacza komplet do ponownej wysyłki. Zwraca
        ścieżki niezależnie od tego, czy plik nadal istnieje — filtruje
        dopiero wywołujący (istniejące → wysyłamy, brakujące → portal skasuje
        przez replace_snapshot)."""
        # RW, bo _ensure_pushed_files_table może zrobić ALTER (read-only by padło).
        con = self._open_master(readonly=False)
        try:
            self._ensure_pushed_files_table(con)
            rows = con.execute(
                'SELECT path FROM rfq_pushed_files WHERE rfq_id=? AND drawing_number=? '
                'ORDER BY filename', (rfq_id, drawing_number)
            ).fetchall()
            return [r['path'] for r in rows]
        finally:
            con.close()

    def check_drawing_freshness(self, rfq_id: int) -> dict:
        """Sprawdza, czy pliki źródłowe na V:\\ zmieniły się od wysłania do RFQ.

        Zwraca {drawing_number: {'status': 'ok'|'changed'|'missing',
                                 'changed_files': [nazwy...],
                                 'missing_files': [nazwy...]}}
        — tylko dla pozycji z zapisanymi odciskami (wysłanych z tego RM_BAZA).

        Hybryda tania→pewna: najpierw size+mtime_ns (sam os.stat, bez czytania
        zawartości). Gdy się różnią, liczy sha1 zawartości:
        - hash TAKI SAM  → to samo (plik skopiowany/przywrócony) → nie alarmuj,
          cicho aktualizujemy size/mtime_ns, żeby następnym razem było tanio;
        - hash INNY       → treść realnie zmieniona → 'changed', plik na liście.

        Hash liczymy ze STABILNEGO odczytu (stat→read→stat): jeśli size/mtime_ns
        drgnęły w trakcie (plik właśnie zapisywany, np. Inventor), NIE oceniamy —
        pomijamy tym razem, sprawdzi się przy następnym Odśwież.

        'missing' (RYS BRAK) rozróżniamy od padniętego V:\\: brak pliku liczy się
        jako missing TYLKO gdy jakiś inny plik dał się odczytać (zasób żyje →
        plik skasowano/przemianowano). Gdy ŻADEN plik nie do odczytu → cały
        zasób niedostępny → pusty wynik (brak alarmu).

        Status per pozycja: 'changed' > 'missing' > 'ok'. Wyłącznie lokalne I/O
        (dysk), bez sieci/portalu. Wołana z GUI w wątku z opóźnieniem."""
        con = self._open_master(readonly=False)
        try:
            self._ensure_pushed_files_table(con)
            rows = con.execute(
                'SELECT path, filename, drawing_number, size, mtime_ns, sha1 '
                'FROM rfq_pushed_files WHERE rfq_id=?', (rfq_id,)
            ).fetchall()
            if not rows:
                return {}

            # per drawing_number: zbieramy flagi i listy zmienionych/brakujących
            agg: dict = {}   # dn -> {'changed': bool, 'missing': bool, 'ok': bool,
                             #        'changed_files': [], 'missing_files': []}
            fixes = []       # (size, mtime_ns, path) — cicha aktualizacja odcisku
            any_readable = False

            def _slot(dn):
                return agg.setdefault(dn, {'changed': False, 'missing': False,
                                          'ok': False, 'changed_files': [],
                                          'missing_files': []})

            for r in rows:
                path, fn, dn = r['path'], r['filename'], r['drawing_number']
                slot = _slot(dn)
                try:
                    st1 = os.stat(path)
                except OSError:
                    slot['missing'] = True          # kandydat — rozstrzygniemy po pętli
                    if fn not in slot['missing_files']:
                        slot['missing_files'].append(fn)
                    continue

                any_readable = True
                # tania ścieżka: metadane zgadzają się → plik nietknięty
                if st1.st_size == r['size'] and r['mtime_ns'] is not None \
                        and st1.st_mtime_ns == r['mtime_ns']:
                    slot['ok'] = True
                    continue

                # różnica metadanych — potwierdzamy hashem, ale STABILNIE
                try:
                    raw = Path(path).read_bytes()
                    st2 = os.stat(path)
                except OSError:
                    slot['missing'] = True
                    if fn not in slot['missing_files']:
                        slot['missing_files'].append(fn)
                    continue

                if st1.st_size != st2.st_size or st1.st_mtime_ns != st2.st_mtime_ns:
                    # plik zmieniał się PODCZAS odczytu (zapis w toku) — nie
                    # oceniaj teraz, żeby nie policzyć hasha częściowego pliku
                    slot['ok'] = True   # neutralnie; następny Odśwież rozstrzygnie
                    continue

                if hashlib.sha1(raw).hexdigest() == r['sha1']:
                    # ta sama treść, tylko metadane inne (kopia) — nie alarmuj,
                    # podmień odcisk, by następnym razem trafić w tanią ścieżkę
                    fixes.append((st2.st_size, st2.st_mtime_ns, path))
                    slot['ok'] = True
                else:
                    slot['changed'] = True
                    if fn not in slot['changed_files']:
                        slot['changed_files'].append(fn)

            # cały zasób niedostępny (nic się nie odczytało) → brak alarmu
            if not any_readable:
                return {}

            if fixes:
                con.executemany(
                    'UPDATE rfq_pushed_files SET size=?, mtime_ns=? WHERE path=?',
                    fixes)
                con.commit()

            # spłaszcz do statusu wg priorytetu changed > missing > ok
            result = {}
            for dn, s in agg.items():
                if s['changed']:
                    status = 'changed'
                elif s['missing']:
                    status = 'missing'
                else:
                    status = 'ok'
                result[dn] = {'status': status,
                              'changed_files': s['changed_files'],
                              'missing_files': s['missing_files']}
            return result
        finally:
            con.close()

    # --- Kanał 3: wyniki portal → RM_BAZA ----------------------------------

    def pull_full_state(self) -> int:
        """Pobiera stan WSZYSTKICH pozycji RFQ i zapisuje do master.sqlite.
        Potrzebne przy pierwszym uruchomieniu: sync_log zawiera tylko zmiany od
        momentu wdrożenia agenta, więc pozycje sprzed niego nie trafiłyby do
        kolumny WYCENA. Potem wystarczy pull_results() (same zmiany)."""
        resp = requests.get(
            f'{self.portal_url}/api/rfq/state',
            headers=self._headers(), timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        rows = resp.json()

        con = self._open_master(readonly=False)
        try:
            self._ensure_results_table(con)
            for row in rows:
                self._upsert_result(con, row)
            con.commit()
        finally:
            con.close()
        self._set_setting('rfq_last_contact', dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return len(rows)

    def reconcile_results(self) -> int:
        """Pełna synchronizacja rfq_results z portalem + USUNIĘCIE osieroconych.

        pull_full_state tylko dodaje/aktualizuje — nie kasuje wierszy, których
        pozycji nie ma już w portalu (np. śmieci po lokalnych testach RFQ sprzed
        przełączenia na produkcję). Ta metoda pobiera pełny stan produkcyjny
        i usuwa z rfq_results (oraz rfq_activity) wszystko, czego tam nie ma —
        po niej kolumna WYCENA odzwierciedla DOKŁADNIE stan portalu. Bezpieczne:
        dobre rekordy zostają (są w portalu), znikają tylko osierocone.
        Zwraca liczbę usuniętych osieroconych wierszy."""
        resp = requests.get(
            f'{self.portal_url}/api/rfq/state',
            headers=self._headers(), timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        rows = resp.json()
        live_item_ids = [r.get('rfq_item_id') for r in rows if r.get('rfq_item_id') is not None]

        con = self._open_master(readonly=False)
        removed = 0
        try:
            self._ensure_results_table(con)
            # 1) upsert wszystkiego, co jest w portalu
            for row in rows:
                self._upsert_result(con, row)
            # 2) skasuj osierocone (są w master.sqlite, nie ma ich w portalu)
            if live_item_ids:
                placeholders = ','.join('?' * len(live_item_ids))
                cur = con.execute(
                    f'DELETE FROM rfq_results WHERE rfq_item_id NOT IN ({placeholders})',
                    live_item_ids)
                removed = cur.rowcount
                # rfq_activity też czyścimy dla spójności (tabelka aktywności)
                try:
                    con.execute(
                        f'DELETE FROM rfq_activity WHERE rfq_item_id NOT IN ({placeholders})',
                        live_item_ids)
                except Exception:
                    pass  # rfq_activity może nie istnieć w starszej bazie

                # 3) ODCISKI PLIKÓW po RFQ, których nie ma już w portalu.
                #
                # rfq_pushed_files jest kluczowane po rfq_id (nie rfq_item_id),
                # więc czyścimy osobno. Bez tego odciski skasowanego zapytania
                # zostawały na zawsze, a all_stale_drawings() iteruje po
                # DISTINCT rfq_id z tej tabeli — czyli sprawdzała pliki
                # nieistniejącego RFQ i doliczała je do badge'a „do podmiany".
                # Efekt: licznik pokazywał pozycje, których nie ma już w panelu,
                # a każde sprawdzenie świeżości czytało te pliki z dysku
                # sieciowego (najwolniejsza operacja w tym mechanizmie).
                live_rfq_ids = {r.get('rfq_id') for r in rows
                                if r.get('rfq_id') is not None}
                if live_rfq_ids:
                    try:
                        ph_rfq = ','.join('?' * len(live_rfq_ids))
                        cur2 = con.execute(
                            f'DELETE FROM rfq_pushed_files WHERE rfq_id NOT IN ({ph_rfq})',
                            list(live_rfq_ids))
                        if cur2.rowcount:
                            print(f'reconcile: usunieto {cur2.rowcount} odciskow plikow '
                                  f'po skasowanych RFQ')
                    except Exception:
                        pass  # tabela może nie istnieć (agent nigdy nic nie wysłał)
            else:
                # PORTAL ZWRÓCIŁ PUSTO. Dwie możliwości, nie do odróżnienia
                # z samej odpowiedzi:
                #   a) faktycznie skasowano wszystkie RFQ — wtedy czyszczenie OK,
                #   b) portal wystartował na PUSTEJ/INNEJ bazie (nieudany deploy,
                #      config.json wskazujący nie ten plik, świeża instalacja).
                #
                # Przy (b) hurtowe DELETE kasuje CAŁĄ kolumnę WYCENA — i robi to
                # automat chodzący co 10 minut, więc user nawet tego nie kliknął.
                # Odtworzenie wymaga ponownej wysyłki wszystkiego do portalu.
                #
                # Dlatego: kasujemy tylko wtedy, gdy lokalnie też jest pusto
                # (nic do stracenia). Gdy mamy dane, a portal nie — to podejrzane,
                # zostawiamy nietknięte i zapisujemy ślad. Kosztem jest ewentualne
                # przetrzymanie śmieci do czasu, aż ktoś to sprawdzi; korzyścią —
                # brak cichej utraty danych.
                ile_lokalnie = con.execute(
                    'SELECT COUNT(*) FROM rfq_results').fetchone()[0]
                if ile_lokalnie:
                    print(f'reconcile: portal zwrocil 0 pozycji, a lokalnie jest '
                          f'{ile_lokalnie} — NIE kasuje (podejrzenie pustej bazy '
                          f'portalu). Sprawdz portal i config.json.', file=sys.stderr)
                    self._set_setting(
                        'rfq_last_error',
                        f'reconcile wstrzymany: portal zwrocil 0 pozycji, '
                        f'lokalnie {ile_lokalnie} — mozliwa pusta baza portalu')
                    self._set_setting('rfq_last_error_at',
                                      dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    removed = 0
                else:
                    removed = con.execute('DELETE FROM rfq_results').rowcount
                    try:
                        con.execute('DELETE FROM rfq_activity')
                    except Exception:
                        pass
            con.commit()
        finally:
            con.close()
        self._set_setting('rfq_last_contact', dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        return removed

    def pull_results(self) -> int:
        """Pobiera nowe rozstrzygnięcia z portalu i zapisuje do master.sqlite.
        Kursor (rfq_last_sync_id) trzymany w settings — przy restarcie agent
        wznawia od miejsca, w którym skończył, bez duplikatów."""
        after_id = int(self._setting('rfq_last_sync_id', '0') or 0)
        resp = requests.get(
            f'{self.portal_url}/api/sync/changes',
            headers=self._headers(), params={'after_id': after_id}, timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        changes = resp.json()

        # Znacznik "agent skontaktował się z portalem" — zapisywany ZAWSZE po
        # udanym odpytaniu, nawet gdy nie było zmian. Po nim RM_BAZA poznaje,
        # czy integracja żyje. Nie można do tego użyć rfq_results.synced_at:
        # ten zmienia się tylko przy realnych zmianach, więc spokojne RFQ
        # wyglądałoby jak awaria.
        self._set_setting('rfq_last_contact', dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        if not changes:
            return 0

        con = self._open_master(readonly=False)
        try:
            self._ensure_results_table(con)
            applied = 0
            for change in changes:
                # 'rfq_item' = pełny snapshot stanu pozycji (zaproszenia, oferty,
                # rozstrzygnięcie). 'award' = format sprzed 29.08.2026, obsługiwany
                # dla wpisów, które mogły zostać w sync_log ze starej wersji.
                if change.get('entity_type') not in ('rfq_item', 'award'):
                    continue
                payload = json.loads(change['payload']) if change.get('payload') else {}
                if not payload.get('drawing_number'):
                    # pozycja skasowana w portalu — usuń też u nas
                    con.execute('DELETE FROM rfq_results WHERE rfq_item_id=?',
                                (payload.get('rfq_item_id'),))
                else:
                    self._upsert_result(con, payload)
                applied += 1
            con.commit()
        finally:
            con.close()

        self._set_setting('rfq_last_sync_id', str(changes[-1]['id']))
        return applied

    def run_auto_reminders(self) -> list:
        """Uruchamia w portalu automatyczne ponowienia zapytań (tylko dla RFQ
        z zaznaczonym „przypominaj automatycznie").

        Portal nie ma własnego schedulera, a agent i tak chodzi co minutę —
        wołamy to RAZ DZIENNIE, bo częściej nie ma sensu: limit jednego
        przypomnienia na kooperanta i tak nie pozwoli wysłać drugiego.
        Znacznik ostatniego uruchomienia trzymamy w master.sqlite → settings."""
        dzis = dt.date.today().isoformat()
        if self._setting('rfq_reminders_last_run', '') == dzis:
            return []          # już dziś sprawdzone
        resp = requests.post(
            f'{self.portal_url}/api/reminders/run',
            headers=self._headers(), timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        self._set_setting('rfq_reminders_last_run', dzis)
        return (resp.json() or {}).get('sent', [])

    def pull_activity(self) -> int:
        """Aktywność kooperantów per pozycja → tabela rfq_activity w master.sqlite.
        RM_BAZA pokazuje z tego tabelkę w oknie Wycena: kto dostał zapytanie,
        czy je otworzył, czy widział TĘ pozycję i czy złożył ofertę.

        Pobierane w całości (nie przyrostowo) — danych jest mało, a dzięki temu
        znikają wiersze po odpiętych kooperantach i skasowanych pozycjach."""
        resp = requests.get(
            f'{self.portal_url}/api/rfq/activity',
            headers=self._headers(), timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        rows = resp.json()

        con = self._open_master(readonly=False)
        try:
            con.execute('''
                CREATE TABLE IF NOT EXISTS rfq_activity (
                    rfq_item_id     INTEGER NOT NULL,
                    supplier_name   TEXT    NOT NULL,
                    drawing_number  TEXT,
                    item_name       TEXT,
                    email_sent_at   TEXT,      -- kiedy poszło zaproszenie (NULL = nie wysłano)
                    first_viewed_at TEXT,      -- pierwsze otwarcie zapytania
                    last_viewed_at  TEXT,      -- ostatnie otwarcie
                    view_count      INTEGER,   -- ile razy otwierał (0 = nie zajrzał)
                    seen_this_item  INTEGER,   -- 1 = wszedł już po dodaniu tej pozycji
                    has_offer       INTEGER,   -- 1 = złożył ofertę na tę pozycję
                    is_winner       INTEGER,   -- 1 = jego oferta wybrana (zwycięzca)
                    win_price       REAL,      -- cena zwycięskiej oferty
                    offer_price     REAL,      -- cena ZŁOŻONEJ oferty (widoczna przed wyborem zwycięzcy)
                    offer_currency  TEXT,      -- waluta złożonej oferty (np. PLN)
                    offer_lead_time INTEGER,   -- termin realizacji w dniach ze złożonej oferty
                    -- Uwagi kooperanta do oferty: zastrzeżenia zmieniające sens
                    -- ceny („bez obróbki cieplnej", „termin po potwierdzeniu
                    -- materiału"). Bez nich user widział samą kwotę.
                    offer_notes     TEXT,
                    offer_submitted_at TEXT,   -- kiedy wpłynęła (vs files_updated_at)
                    -- ODMOWA wyceny: 1 = kooperant świadomie odmówił. Bez tego
                    -- "brak oferty" i "odmowa" wyglądały w RM_BAZA identycznie
                    -- ("—"), a to różnica między "czekamy" a "szukaj kogoś innego".
                    has_declined    INTEGER,
                    decline_reason  TEXT,      -- kod z listy zamkniętej (brak_mocy, termin, …)
                    decline_label   TEXT,      -- gotowa etykieta PL z portalu (nie tłumaczymy u siebie)
                    decline_notes   TEXT,      -- własne wyjaśnienie kooperanta (zwykle przy „inne")
                    declined_at     TEXT,      -- kiedy odmówił
                    synced_at       TEXT DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (rfq_item_id, supplier_name)
                )
            ''')
            # migracja istniejącej tabeli (sprzed oznaczania zwycięzcy)
            akt_cols = {r[1] for r in con.execute('PRAGMA table_info(rfq_activity)')}
            for col, decl in (('is_winner', 'INTEGER'), ('win_price', 'REAL'),
                              ('offer_price', 'REAL'), ('offer_currency', 'TEXT'),
                              ('offer_lead_time', 'INTEGER'),
                              ('has_declined', 'INTEGER'), ('decline_reason', 'TEXT'),
                              ('decline_label', 'TEXT'), ('decline_notes', 'TEXT'),
                              ('declined_at', 'TEXT'),
                              ('offer_notes', 'TEXT'), ('offer_submitted_at', 'TEXT')):
                if col not in akt_cols:
                    con.execute(f'ALTER TABLE rfq_activity ADD COLUMN {col} {decl}')
            con.execute('CREATE INDEX IF NOT EXISTS idx_rfq_activity_drawing '
                        'ON rfq_activity(drawing_number)')
            # pełna podmiana — patrz docstring
            con.execute('DELETE FROM rfq_activity')
            con.executemany('''
                INSERT OR REPLACE INTO rfq_activity (
                    rfq_item_id, supplier_name, drawing_number, item_name,
                    email_sent_at, first_viewed_at, last_viewed_at,
                    view_count, seen_this_item, has_offer, is_winner, win_price,
                    offer_price, offer_currency, offer_lead_time,
                    has_declined, decline_reason, decline_label, decline_notes,
                    declined_at, offer_notes, offer_submitted_at, synced_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now','localtime'))
            ''', [
                (r.get('rfq_item_id'), r.get('supplier_name'), r.get('drawing_number'),
                 r.get('item_name'), r.get('email_sent_at'), r.get('first_viewed_at'),
                 r.get('last_viewed_at'), r.get('view_count'),
                 r.get('seen_this_item'), r.get('has_offer'),
                 r.get('is_winner'), r.get('win_price'),
                 r.get('offer_price'), r.get('offer_currency'), r.get('offer_lead_time'),
                 r.get('has_declined'), r.get('decline_reason'),
                 r.get('decline_reason_label'), r.get('decline_notes'),
                 r.get('declined_at'),
                 r.get('offer_notes'), r.get('offer_submitted_at'))
                for r in rows
            ])
            con.commit()
        finally:
            con.close()
        return len(rows)

    @staticmethod
    def _ensure_results_table(con: sqlite3.Connection) -> None:
        """Stan ofertowania w master.sqlite — jedna pozycja RFQ = jeden wiersz.
        Zawiera też pozycje jeszcze nierozstrzygnięte (liczniki zaproszeń/ofert),
        bo kolumna WYCENA w tksheet pokazuje stany pośrednie:
        "WYSŁANO · 4" → "1/4 OFERT · 96 zł" → "✓ ABC CNC · 85 zł"."""
        con.execute('''
            CREATE TABLE IF NOT EXISTS rfq_results (
                rfq_item_id      INTEGER PRIMARY KEY,
                drawing_number   TEXT NOT NULL,
                item_name        TEXT,
                revision         INTEGER,
                quantity         INTEGER,
                material         TEXT,
                project_number   TEXT,
                rfq_id           INTEGER,   -- do linku 'Przejdź do RFQ' w RM_BAZA
                rfq_code         TEXT,
                rfq_title        TEXT,
                rfq_status       TEXT,
                suppliers_count  INTEGER,   -- ilu kooperantów widzi tę pozycję
                offers_count     INTEGER,   -- ile ofert wpłynęło
                declined_count   INTEGER,   -- ilu kooperantów odmówiło wyceny
                min_price        REAL,      -- najtańsza oferta (do stanu pośredniego)
                invitations_sent INTEGER,   -- do ilu wysłano zaproszenia
                response_deadline TEXT,     -- termin odpowiedzi (kolor komórki WYCENA)
                files_updated_at TEXT,      -- kiedy podmieniono dokumentację (replace_snapshot)
                docs_notified_at TEXT,      -- kiedy powiadomiono kooperantów o tej wersji
                viewers_count    INTEGER,   -- ilu z nich otworzyło zapytanie w portalu
                seen_item_count  INTEGER,   -- ilu widziało TĘ pozycję (weszło po jej dodaniu)
                last_viewed_at   TEXT,      -- ostatnie wejście któregokolwiek z przypisanych
                supplier_id      INTEGER,   -- poniżej: dane zwycięzcy (NULL gdy brak)
                supplier_name    TEXT,
                price            REAL,
                currency         TEXT,
                lead_time_days   INTEGER,
                offer_notes      TEXT,
                decided_at       TEXT,
                synced_at        TEXT DEFAULT (datetime('now','localtime'))
            )
        ''')
        con.execute(
            'CREATE INDEX IF NOT EXISTS idx_rfq_results_drawing ON rfq_results(drawing_number)'
        )
        # migracja starszej wersji tabeli (sprzed kolumny WYCENA ze stanami pośrednimi)
        existing = {r[1] for r in con.execute('PRAGMA table_info(rfq_results)')}
        for col, decl in (
            ('rfq_id', 'INTEGER'), ('rfq_status', 'TEXT'), ('suppliers_count', 'INTEGER'),
            ('offers_count', 'INTEGER'), ('min_price', 'REAL'),
            ('invitations_sent', 'INTEGER'),
            ('viewers_count', 'INTEGER'), ('seen_item_count', 'INTEGER'),
            ('last_viewed_at', 'TEXT'), ('response_deadline', 'TEXT'),
            ('declined_count', 'INTEGER'),
            ('files_updated_at', 'TEXT'), ('docs_notified_at', 'TEXT'),
        ):
            if col not in existing:
                con.execute(f'ALTER TABLE rfq_results ADD COLUMN {col} {decl}')

    @staticmethod
    def _upsert_result(con: sqlite3.Connection, p: dict[str, Any]) -> None:
        con.execute('''
            INSERT INTO rfq_results (
                rfq_item_id, drawing_number, item_name, revision, quantity, material,
                project_number, rfq_id, rfq_code, rfq_title, rfq_status,
                suppliers_count, offers_count, declined_count, min_price, invitations_sent,
                viewers_count, seen_item_count, last_viewed_at, response_deadline,
                files_updated_at, docs_notified_at,
                supplier_id, supplier_name, price, currency, lead_time_days,
                offer_notes, decided_at, synced_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now','localtime'))
            ON CONFLICT(rfq_item_id) DO UPDATE SET
                drawing_number=excluded.drawing_number, item_name=excluded.item_name,
                revision=excluded.revision, quantity=excluded.quantity,
                material=excluded.material, project_number=excluded.project_number,
                rfq_id=excluded.rfq_id,
                rfq_code=excluded.rfq_code, rfq_title=excluded.rfq_title,
                rfq_status=excluded.rfq_status, suppliers_count=excluded.suppliers_count,
                offers_count=excluded.offers_count, declined_count=excluded.declined_count,
                min_price=excluded.min_price,
                invitations_sent=excluded.invitations_sent,
                viewers_count=excluded.viewers_count,
                seen_item_count=excluded.seen_item_count,
                last_viewed_at=excluded.last_viewed_at,
                response_deadline=excluded.response_deadline,
                files_updated_at=excluded.files_updated_at,
                docs_notified_at=excluded.docs_notified_at,
                supplier_id=excluded.supplier_id, supplier_name=excluded.supplier_name,
                price=excluded.price, currency=excluded.currency,
                lead_time_days=excluded.lead_time_days, offer_notes=excluded.offer_notes,
                decided_at=excluded.decided_at, synced_at=excluded.synced_at
        ''', (
            p.get('rfq_item_id'), p.get('drawing_number'), p.get('item_name'),
            p.get('revision'), p.get('quantity'), p.get('material'),
            p.get('project_number'), p.get('rfq_id'), p.get('rfq_code'), p.get('rfq_title'),
            p.get('rfq_status'), p.get('suppliers_count'), p.get('offers_count'),
            p.get('declined_count'), p.get('min_price'), p.get('invitations_sent'),
            p.get('viewers_count'), p.get('seen_item_count'), p.get('last_viewed_at'),
            p.get('response_deadline'),
            p.get('files_updated_at'), p.get('docs_notified_at'),
            p.get('supplier_id'), p.get('supplier_name'), p.get('price'),
            p.get('currency'), p.get('lead_time_days'), p.get('offer_notes'),
            p.get('decided_at'),
        ))


def main() -> int:
    parser = argparse.ArgumentParser(description='RM_SYNC_AGENT — synchronizacja RM_BAZA ↔ RM_RFQ')
    parser.add_argument('--master', default=MASTER_DB_DEFAULT, help='ścieżka do master.sqlite')
    parser.add_argument('--once', action='store_true', help='jeden przebieg (kanały 1 i 3) i wyjście')
    parser.add_argument('--suppliers-only', action='store_true', help='tylko wypchnij kooperantów')
    parser.add_argument('--results-only', action='store_true', help='tylko pobierz wyniki')
    parser.add_argument('--full-state', action='store_true',
                        help='pobierz stan WSZYSTKICH pozycji RFQ (pierwsze uruchomienie)')
    parser.add_argument('--reconcile', action='store_true',
                        help='pełna synchronizacja + usunięcie osieroconych rekordów (czyszczenie śmieci)')
    args = parser.parse_args()

    try:
        agent = RMSyncAgent(args.master)
    except Exception as e:
        print(f'BLAD konfiguracji: {e}', file=sys.stderr)
        return 2

    exit_code = 0

    # Agent chodzi z Task Schedulera przez sync_agent_hidden.vbs — BEZ OKNA
    # KONSOLI, więc wszystko, co leci na stderr, przepada. Bez zapisu do bazy
    # awaria (403 na kluczu, padnięty portal, zablokowany master.sqlite) jest
    # dla użytkownika NIEWIDOCZNA: RM_BAZA umiało pokazać tylko „minęła godzina
    # od ostatniego kontaktu", nigdy powodu. Zapisujemy więc ostatni błąd do
    # settings — RM_BAZA czyta to i pokazuje konkret zamiast „brak danych".
    def _zapisz_blad(opis: str, wyjatek: Exception) -> None:
        tekst = f'{opis}: {type(wyjatek).__name__}: {wyjatek}'
        print(f'BLAD {tekst}', file=sys.stderr)
        try:
            agent._set_setting('rfq_last_error', tekst[:500])
            agent._set_setting('rfq_last_error_at',
                               dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        except Exception:
            pass        # nie udało się zapisać błędu — nie maskujemy nim pierwotnego

    def _wyczysc_blad() -> None:
        """Pełny cykl bez wpadki — kasujemy ślad, żeby stary błąd nie straszył."""
        try:
            if agent._setting('rfq_last_error', ''):
                agent._set_setting('rfq_last_error', '')
                agent._set_setting('rfq_last_error_at', '')
        except Exception:
            pass

    if args.full_state:
        try:
            print(f'Pelny stan pobrany: {agent.pull_full_state()} pozycji')
        except Exception as e:
            _zapisz_blad('pobierania pelnego stanu', e)
            exit_code = 1
        return exit_code

    if args.reconcile:
        try:
            print(f'Reconcile: usunieto {agent.reconcile_results()} osieroconych rekordow')
        except Exception as e:
            _zapisz_blad('reconcile', e)
            exit_code = 1
        return exit_code

    if not args.results_only:
        try:
            print(f'Kooperanci wyslani: {agent.push_suppliers()}')
        except Exception as e:
            _zapisz_blad('kanalu kooperantow', e)
            exit_code = 1

    if not args.suppliers_only:
        try:
            print(f'Wyniki pobrane: {agent.pull_results()}')
        except Exception as e:
            _zapisz_blad('kanalu wynikow', e)
            exit_code = 1

        # aktywność kooperantów — osobno, bo błąd tutaj nie może wywalić
        # synchronizacji wyników (to dane pomocnicze do okna Wycena)
        try:
            print(f'Aktywnosc kooperantow: {agent.pull_activity()}')
        except Exception as e:
            _zapisz_blad('kanalu aktywnosci', e)
            exit_code = 1

        # Automatyczne ponowienia — tylko dla RFQ z zaznaczonym auto_reminder.
        # Raz dziennie (znacznik w settings), osobny try: blad wysylki maili
        # nie moze wywalic synchronizacji danych.
        try:
            wyslane = agent.run_auto_reminders()
            if wyslane:
                print(f'Ponowienia automatyczne: {"; ".join(wyslane)}')
        except Exception as e:
            print(f'BLAD ponowien: {e}', file=sys.stderr)

        # SIATKA BEZPIECZENSTWA: co ~10 min pelny reconcile. pull_results
        # (przyrostowy, co cykl) lapie tylko zmiany zalogowane do sync_log —
        # gdyby jakas trasa portalu zapomniala zalogowac (albo doszla nowa),
        # reconcile wyrownuje CALY stan z portalem. Rzadko (10 min), zeby nie
        # kasowac osieroconych zbyt czesto ani nie obciazac lacza (metadane, nie pliki).
        try:
            last = agent._setting('rfq_last_reconcile', '')
            do_reconcile = True
            if last:
                try:
                    delta = dt.datetime.now() - dt.datetime.fromisoformat(last)
                    do_reconcile = delta.total_seconds() >= 600  # 10 min
                except Exception:
                    do_reconcile = True
            if do_reconcile:
                removed = agent.reconcile_results()
                agent._set_setting('rfq_last_reconcile', dt.datetime.now().isoformat())
                print(f'Reconcile (siatka bezp.): usunieto {removed} osieroconych')
        except Exception as e:
            print(f'BLAD reconcile (siatka): {e}', file=sys.stderr)
            # nie podnosimy exit_code — to tylko siatka, glowny sync juz przeszedl

    # Cykl bez wpadki — kasujemy ślad po poprzednim błędzie, żeby RM_BAZA nie
    # pokazywało nieaktualnego ostrzeżenia po tym, jak problem sam minął
    # (np. portal wrócił po restarcie).
    if exit_code == 0:
        _wyczysc_blad()

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
