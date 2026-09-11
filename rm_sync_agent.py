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
    ┌────────────────────────────────┐            ┌────────────────────┐
    │ RM_SERWER ──► master.sqlite    │            │  RM_RFQ (Flask)    │
    │     ▲              (na dysku   │            │  rm_rfq.db         │
    │     │ TCP 5060      serwera)   │            │        ▲           │
    │  RM_SYNC_AGENT ────► V:\ (pliki)┼───────────►│  API + X-API-Key   │
    └────────────────────────────────┘  HTTPS out └────────────────────┘

    ⚠️ Dwa różne dostępy, nie mylić:
      • METADANE (settings, wyniki, odciski) — przez RM_SERWER, nazwanymi
        operacjami. Agent NIE otwiera master.sqlite jako pliku.
      • PLIKI rysunków — czytane wprost z V:\ i wysyłane treścią do portalu.
        To zostaje bez zmian do etapu 3 planu (patrz PLAN_RM_SERWER.md).

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
Wszystko w master.sqlite → tabela settings (klucz/wartość), czytane
przez RM_SERWER:
    rfq_portal_url   — np. https://oferty.rmpak.pl
    rfq_api_key      — ten sam klucz co RM_RFQ/config.json → rm_baza_api_key
    rfq_last_sync_id — kursor kanału 3, agent aktualizuje go sam

Adres samego RM_SERWER bierze się z `sync_config.json` (klucz `rm_serwer`) —
jak w RM_BAZA. Gdy serwer nie odpowiada, agent kończy błędem i Task Scheduler
spróbuje w następnym cyklu; NIE ma trybu awaryjnego na plik, bo dwa procesy
piszące do jednego SQLite to dokładnie ten problem, który serwer usuwa.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

import rm_klient

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


def _skonfiguruj_serwer() -> None:
    """Adres RM_SERWER z `sync_config.json` — ten sam plik co RM_BAZA.

    Wołane raz; `rm_klient` trzyma konfigurację globalnie, więc powtórne
    wywołanie jest nieszkodliwe (agent bywa importowany przez GUI RM_BAZA,
    które skonfigurowało klienta wcześniej).
    """
    if rm_klient.skonfigurowany():
        return
    # Ta sama ścieżka i ten sam klucz co w RM_BAZA (`database_manager`)
    # i RM_MANAGER — jedna konfiguracja dla wszystkich klientów serwera.
    # utf-8-sig, bo plik bywa zapisywany z BOM-em.
    cfg = {}
    try:
        cfg = json.loads(Path(r'C:\RMPAK_CLIENT\sync_config.json')
                         .read_text(encoding='utf-8-sig'))
    except Exception:
        pass
    serwer = (cfg.get('rm_serwer') or {}) if isinstance(cfg, dict) else {}
    host = serwer.get('host')
    if not host:
        raise RuntimeError(
            'Brak adresu RM_SERWER w sync_config.json (klucz "rm_serwer" → "host"). '
            'Agent nie ma innej drogi do master.sqlite.')
    rm_klient.ustaw_serwer(host, serwer.get('port'), serwer.get('sekret'))
    rm_klient.ustaw_uzytkownika('RM_SYNC_AGENT')


class RMSyncAgent:
    def __init__(self):
        _skonfiguruj_serwer()
        self.portal_url = self._portal_url_for_machine()
        self.api_key = self._setting('rfq_api_key', '')
        if not self.portal_url or not self.api_key:
            raise RuntimeError(
                'Brak konfiguracji w master.sqlite → settings: '
                'ustaw rfq_portal_url i rfq_api_key'
            )

    # --- dostęp do mastera: WYŁĄCZNIE przez RM_SERWER -----------------------
    #
    # Nie ma tu `_open_master()`. Master leży na dysku serwera i uchwyt do
    # pliku ma jeden proces — RM_SERWER. Każda operacja jest nazwana
    # (`rm_serwer_operacje.ODCZYT` / `.ZAPIS`); agent nie wysyła SQL, bo
    # serwer słucha na LAN, a furtka na dowolny SQL to `DROP TABLE`
    # z dowolnej maszyny w sieci.

    @staticmethod
    def _czytaj(operacja: str, params: dict = None) -> list[dict]:
        return rm_klient.master_read(operacja, params)

    @staticmethod
    def _zapisz(operacja: str, params: dict = None) -> dict:
        return rm_klient.master_exec(operacja, params)

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
        wiersze = self._czytaj('rfq-ustawienie', {'key': key})
        wartosc = wiersze[0]['value'] if wiersze else None
        return wartosc if wartosc is not None else default

    def _set_setting(self, key: str, value: str) -> None:
        self._zapisz('rfq-ustawienie-zapisz', {'key': key, 'value': value})

    # --- HTTP ---------------------------------------------------------------

    def _headers(self) -> dict:
        return {'X-API-Key': self.api_key}

    # --- Kanał 1: kooperanci → portal --------------------------------------

    def push_suppliers(self) -> int:
        """Czyta suppliers z master.sqlite i wypycha pełną listę do portalu.
        Portal robi upsert po supplier_id, więc nie musimy śledzić zmian."""
        # `suppliers-list` to `SELECT *` — aliasowanie kolumn robimy tutaj,
        # po nazwach w zwróconym wierszu. Wcześniej szło to przez
        # `PRAGMA table_info` i sklejany SELECT; schemat rozpoznajemy dalej
        # dynamicznie (kolumny różnią się między instalacjami), tylko bez
        # budowania SQL po stronie klienta.
        rows = self._czytaj('suppliers-list')
        cols = set(rows[0].keys()) if rows else set()
        if not cols:
            raise RuntimeError('Tabela suppliers jest pusta albo nie istnieje')
        col_map = {k: _pick_column(cols, aliases)
                   for k, aliases in SUPPLIER_COLUMN_ALIASES.items()}
        if not col_map['name']:
            raise RuntimeError('Nie znaleziono kolumny z nazwą firmy w suppliers')

        # Tagi kooperantów: słownik + przypisania (RM_BAZA jest właścicielem,
        # portal RM_RFQ tylko czyta kopię). Puste, gdy tabel jeszcze nie ma
        # (starsza baza) — sync dostawców ma działać niezależnie od tagów.
        tags_dict, tag_ids_by_supplier = [], {}
        try:
            tags_dict = [dict(r) for r in self._czytaj('rfq-tagi')]
            for r in self._czytaj('rfq-tagi-dostawcow'):
                tag_ids_by_supplier.setdefault(r['supplier_id'], []).append(r['tag_id'])
        except Exception:
            pass

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


    def _store_pushed_fingerprints(self, rfq_id: int, drawing_number: str,
                                   file_paths: list[str], fingerprints: list) -> None:
        # Odciski dla tej pozycji zastępujemy w całości: jeśli user wyśle ją
        # ponownie z innym zestawem plików, stare (odpięte) pliki nie mają
        # już wisieć jako „zmienione".
        #
        # DELETE i INSERT-y lecą JEDNYM batchem, czyli jedną transakcją —
        # inaczej zerwane połączenie między nimi zostawiłoby pozycję bez
        # odcisków i każdy jej plik wyglądałby na „brakujący".
        operacje = [{'operation': 'rfq-pushed-czysc-pozycje',
                     'params': {'rfq_id': rfq_id, 'drawing_number': drawing_number}}]
        operacje += [
            {'operation': 'rfq-pushed-dodaj',
             'params': {'rfq_id': rfq_id, 'drawing_number': drawing_number,
                        'path': str(path), 'filename': fn, 'size': size,
                        'mtime_ns': mtime_ns, 'sha1': sha1}}
            for path, (fn, size, mtime_ns, sha1) in zip(file_paths, fingerprints)
        ]
        rm_klient.master_batch(operacje)

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
        rfq_ids = [r['rfq_id'] for r in self._czytaj('rfq-pushed-rfq-id')]

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
        # Kolumn `files_updated_at`/`docs_notified_at` pilnują migracje
        # serwera, więc nie ma już sprawdzania PRAGMA „czy stara baza".
        out = [dict(r) for r in self._czytaj('rfq-do-powiadomienia')]

        # Nazwa detalu: portal często NIE ma jej w rfq_items.name (jest tylko
        # sklejana z nazwy pliku), więc item_name z bazy bywa NULL. Wyciągamy
        # ją z nazwy WYSŁANEGO pliku (rfq_pushed_files) — te dane są lokalnie,
        # zero dodatkowego I/O. Format pliku: "<numer rysunku> <nazwa>.<ext>".
        for d in out:
            if d.get('item_name'):
                continue
            d['item_name'] = self._name_from_pushed_files(
                d['rfq_id'], d['drawing_number']) or None
        return out

    def _name_from_pushed_files(self, rfq_id, drawing_number) -> str:
        """Wydłubuje nazwę detalu z nazwy wysłanego pliku (rfq_pushed_files).
        Preferuje PDF/DWF (czysta nazwa bez dopisków typu ", 304 gr8mm" na DXF).
        Zwraca '' gdy nie da się wyznaczyć."""
        rows = self._czytaj('rfq-pushed-nazwy',
                            {'rfq_id': rfq_id, 'drawing_number': drawing_number})
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
        rows = self._czytaj('rfq-pushed-sciezki',
                            {'rfq_id': rfq_id, 'drawing_number': drawing_number})
        return [r['path'] for r in rows]

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
        rows = self._czytaj('rfq-pushed-odciski', {'rfq_id': rfq_id})
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
            # Cicha aktualizacja odcisków (ta sama treść, inne metadane).
            # Nieudany zapis NIE jest błędem tej metody: to optymalizacja,
            # żeby następnym razem wystarczył sam os.stat. Bez niej wynik
            # jest ten sam, tylko liczony drożej.
            try:
                rm_klient.master_batch([
                    {'operation': 'rfq-pushed-odswiez-odcisk',
                     'params': {'size': size, 'mtime_ns': mtime_ns, 'path': path}}
                    for size, mtime_ns, path in fixes])
            except rm_klient.BladSerwera:
                pass

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

        # Jeden batch = jedna transakcja: albo wchodzi cały stan z portalu,
        # albo nic. Połowicznie zapisany stan dałby w RM_BAZA mieszankę
        # nowych i starych wycen, nie do odróżnienia na oko.
        if rows:
            rm_klient.master_batch([self._operacja_wyniku(r) for r in rows])
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

        removed = 0
        if live_item_ids:
            # Wszystko jednym batchem = jedna transakcja: upsert stanu
            # i skasowanie osieroconych albo wchodzi razem, albo wcale.
            #
            # ⚠️ Listy żywych identyfikatorów NIE sklejamy w `NOT IN (?,?,?…)` —
            # jadą jako jeden parametr (tablica JSON, rozpakowana po stronie
            # serwera przez json_each). Klient nie wysyła SQL.
            operacje = [self._operacja_wyniku(r) for r in rows]
            operacje.append({'operation': 'rfq-wyniki-reconcile',
                             'params': {'zywe_json': json.dumps(live_item_ids)}})
            operacje.append({'operation': 'rfq-aktywnosc-reconcile',
                             'params': {'zywe_json': json.dumps(live_item_ids)}})

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
                operacje.append({
                    'operation': 'rfq-pushed-reconcile',
                    'params': {'zywe_json': json.dumps(sorted(live_rfq_ids))}})

            wyniki = rm_klient.master_batch(operacje)
            # Ile skasowano: rowcount operacji `rfq-wyniki-reconcile`. Leży
            # bezpośrednio po upsertach, stąd indeks liczony od ich liczby.
            try:
                removed = wyniki[len(rows)].get('rowcount') or 0
            except (IndexError, AttributeError, TypeError):
                removed = 0
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
            wiersze = self._czytaj('rfq-wynikow-ile')
            ile_lokalnie = wiersze[0]['n'] if wiersze else 0
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
                wyniki = rm_klient.master_batch([
                    {'operation': 'rfq-wyniki-wyczysc', 'params': {}},
                    {'operation': 'rfq-aktywnosc-wyczysc', 'params': {}},
                ])
                removed = (wyniki[0].get('rowcount') or 0) if wyniki else 0
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

        operacje = []
        for change in changes:
            # 'rfq_item' = pełny snapshot stanu pozycji (zaproszenia, oferty,
            # rozstrzygnięcie). 'award' = format sprzed 29.08.2026, obsługiwany
            # dla wpisów, które mogły zostać w sync_log ze starej wersji.
            if change.get('entity_type') not in ('rfq_item', 'award'):
                continue
            payload = json.loads(change['payload']) if change.get('payload') else {}
            if not payload.get('drawing_number'):
                # pozycja skasowana w portalu — usuń też u nas
                operacje.append({'operation': 'rfq-wynik-usun',
                                 'params': {'rfq_item_id': payload.get('rfq_item_id')}})
            else:
                operacje.append(self._operacja_wyniku(payload))
        applied = len(operacje)
        # Kursor (`rfq_last_sync_id`) przesuwamy DOPIERO po udanym batchu —
        # gdyby zapis padł, następny przebieg pobierze te same zmiany jeszcze
        # raz. Powtórka jest nieszkodliwa (upsert po kluczu), a zgubiona
        # zmiana nie wróciłaby już nigdy.
        if operacje:
            rm_klient.master_batch(operacje)

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

        # Pełna podmiana (patrz docstring): kasujemy wszystko i wstawiamy
        # świeży stan — JEDNYM batchem, czyli jedną transakcją. Gdyby DELETE
        # wszedł, a INSERT-y nie, RM_BAZA pokazałaby pustą tabelkę aktywności
        # przy żywych zapytaniach.
        #
        # Schematu nie dotykamy: tabelę i jej kolumny tworzą migracje serwera.
        operacje = [{'operation': 'rfq-aktywnosc-wyczysc', 'params': {}}]
        for r in rows:
            p = {k: r.get(k) for k in (
                'rfq_item_id', 'supplier_name', 'drawing_number', 'item_name',
                'email_sent_at', 'first_viewed_at', 'last_viewed_at',
                'view_count', 'seen_this_item', 'has_offer', 'is_winner',
                'win_price', 'offer_price', 'offer_currency', 'offer_lead_time',
                'has_declined', 'decline_reason', 'decline_notes', 'declined_at',
                'offer_notes', 'offer_submitted_at')}
            # ⚠️ Portal nazywa to `decline_reason_label`, kolumna u nas to
            # `decline_label`. Nie zmieniać na pętlę po wspólnych nazwach —
            # ta jedna się nie zgadza i etykieta odmowy zniknęłaby z GUI.
            p['decline_label'] = r.get('decline_reason_label')
            operacje.append({'operation': 'rfq-aktywnosc-zapisz', 'params': p})
        rm_klient.master_batch(operacje)
        return len(rows)


    @staticmethod
    def _operacja_wyniku(p: dict[str, Any]) -> dict:
        """Opis operacji zapisu jednej pozycji — do batcha.

        Zwraca `{'operation': ..., 'params': ...}`, a nie wykonuje zapisu:
        wołający zbiera je w listę i wysyła JEDNYM batchem, żeby cały stan
        z portalu wszedł w jednej transakcji.
        """
        return {
            'operation': 'rfq-wynik-zapisz',
            'params': {k: p.get(k) for k in (
                'rfq_item_id', 'drawing_number', 'item_name', 'revision',
                'quantity', 'material', 'project_number', 'rfq_id', 'rfq_code',
                'rfq_title', 'rfq_status', 'suppliers_count', 'offers_count',
                'declined_count', 'min_price', 'invitations_sent',
                'viewers_count', 'seen_item_count', 'last_viewed_at',
                'response_deadline', 'files_updated_at', 'docs_notified_at',
                'supplier_id', 'supplier_name', 'price', 'currency',
                'lead_time_days', 'offer_notes', 'decided_at')},
        }



def main() -> int:
    parser = argparse.ArgumentParser(description='RM_SYNC_AGENT — synchronizacja RM_BAZA ↔ RM_RFQ')
    # Master leży na dysku serwera; ścieżki do pliku nie ma już jak podać.
    # `--serwer HOST[:PORT]` nadpisuje adres z sync_config.json — do testów
    # i do wskazania zapasowego serwera bez ruszania konfiguracji.
    parser.add_argument('--serwer', default=None,
                        help='adres RM_SERWER, np. 192.168.100.84:5060 '
                             '(domyślnie z sync_config.json)')
    parser.add_argument('--once', action='store_true', help='jeden przebieg (kanały 1 i 3) i wyjście')
    parser.add_argument('--suppliers-only', action='store_true', help='tylko wypchnij kooperantów')
    parser.add_argument('--results-only', action='store_true', help='tylko pobierz wyniki')
    parser.add_argument('--full-state', action='store_true',
                        help='pobierz stan WSZYSTKICH pozycji RFQ (pierwsze uruchomienie)')
    parser.add_argument('--reconcile', action='store_true',
                        help='pełna synchronizacja + usunięcie osieroconych rekordów (czyszczenie śmieci)')
    args = parser.parse_args()

    if args.serwer:
        host, _, port = args.serwer.partition(':')
        rm_klient.ustaw_serwer(host, int(port) if port else None)
        rm_klient.ustaw_uzytkownika('RM_SYNC_AGENT')

    try:
        agent = RMSyncAgent()
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
