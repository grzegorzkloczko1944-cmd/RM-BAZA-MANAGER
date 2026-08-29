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
import json
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
        self.portal_url = self._setting('rfq_portal_url', '').rstrip('/')
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
            con = sqlite3.connect(f'file:{uri}?mode=ro', uri=True, timeout=10)
        else:
            con = sqlite3.connect(self.master_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

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
        finally:
            con.close()

        suppliers = []
        for row in rows:
            values = dict(row)
            suppliers.append({
                'supplier_id': values['supplier_id'],
                'name': values.get(col_map['name']) or '',
                'email': values.get(col_map['email']) if col_map['email'] else None,
                'phone': values.get(col_map['phone']) if col_map['phone'] else None,
                'contact_person': values.get(col_map['contact_person']) if col_map['contact_person'] else None,
                'nip': values.get(col_map['nip']) if col_map['nip'] else None,
                'active': 1 if (values.get(col_map['active']) if col_map['active'] else 1) else 0,
            })

        resp = requests.post(
            f'{self.portal_url}/api/suppliers/sync',
            headers=self._headers(), json={'suppliers': suppliers}, timeout=HTTP_TIMEOUT
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

    def create_rfq(self, title: str, project_number: str | None = None,
                   offer_start_date: str | None = None,
                   offer_deadline: str | None = None) -> dict:
        """Zakłada nowe RFQ w portalu. Zwraca {rfq_id, code, title}."""
        payload = {'title': title}
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

    def push_drawing(self, rfq_id: int, drawing_number: str, file_paths: list[str],
                     name: str | None = None, quantity: int = 1,
                     material: str | None = None, notes: str | None = None) -> dict:
        """Wysyła rysunek jako nową pozycję RFQ. Agent CZYTA pliki lokalnie i
        wysyła ich zawartość — portal nigdy nie dostaje ścieżki ani dostępu do
        dysku firmowego. Wywoływane z GUI RM_BAZA."""
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

        handles = []
        try:
            files = []
            for path in file_paths:
                fh = open(path, 'rb')
                handles.append(fh)
                files.append(('files', (Path(path).name, fh)))
            resp = requests.post(
                f'{self.portal_url}/api/rfq/{rfq_id}/items',
                headers=self._headers(), data=data, files=files, timeout=HTTP_TIMEOUT
            )
        finally:
            for fh in handles:
                fh.close()
        resp.raise_for_status()
        return resp.json()

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
                    synced_at       TEXT DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (rfq_item_id, supplier_name)
                )
            ''')
            # migracja istniejącej tabeli (sprzed oznaczania zwycięzcy)
            akt_cols = {r[1] for r in con.execute('PRAGMA table_info(rfq_activity)')}
            for col, decl in (('is_winner', 'INTEGER'), ('win_price', 'REAL'),
                              ('offer_price', 'REAL'), ('offer_currency', 'TEXT'),
                              ('offer_lead_time', 'INTEGER')):
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
                    offer_price, offer_currency, offer_lead_time, synced_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now','localtime'))
            ''', [
                (r.get('rfq_item_id'), r.get('supplier_name'), r.get('drawing_number'),
                 r.get('item_name'), r.get('email_sent_at'), r.get('first_viewed_at'),
                 r.get('last_viewed_at'), r.get('view_count'),
                 r.get('seen_this_item'), r.get('has_offer'),
                 r.get('is_winner'), r.get('win_price'),
                 r.get('offer_price'), r.get('offer_currency'), r.get('offer_lead_time'))
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
                min_price        REAL,      -- najtańsza oferta (do stanu pośredniego)
                invitations_sent INTEGER,   -- do ilu wysłano zaproszenia
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
            ('last_viewed_at', 'TEXT'),
        ):
            if col not in existing:
                con.execute(f'ALTER TABLE rfq_results ADD COLUMN {col} {decl}')

    @staticmethod
    def _upsert_result(con: sqlite3.Connection, p: dict[str, Any]) -> None:
        con.execute('''
            INSERT INTO rfq_results (
                rfq_item_id, drawing_number, item_name, revision, quantity, material,
                project_number, rfq_id, rfq_code, rfq_title, rfq_status,
                suppliers_count, offers_count, min_price, invitations_sent,
                viewers_count, seen_item_count, last_viewed_at,
                supplier_id, supplier_name, price, currency, lead_time_days,
                offer_notes, decided_at, synced_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now','localtime'))
            ON CONFLICT(rfq_item_id) DO UPDATE SET
                drawing_number=excluded.drawing_number, item_name=excluded.item_name,
                revision=excluded.revision, quantity=excluded.quantity,
                material=excluded.material, project_number=excluded.project_number,
                rfq_id=excluded.rfq_id,
                rfq_code=excluded.rfq_code, rfq_title=excluded.rfq_title,
                rfq_status=excluded.rfq_status, suppliers_count=excluded.suppliers_count,
                offers_count=excluded.offers_count, min_price=excluded.min_price,
                invitations_sent=excluded.invitations_sent,
                viewers_count=excluded.viewers_count,
                seen_item_count=excluded.seen_item_count,
                last_viewed_at=excluded.last_viewed_at,
                supplier_id=excluded.supplier_id, supplier_name=excluded.supplier_name,
                price=excluded.price, currency=excluded.currency,
                lead_time_days=excluded.lead_time_days, offer_notes=excluded.offer_notes,
                decided_at=excluded.decided_at, synced_at=excluded.synced_at
        ''', (
            p.get('rfq_item_id'), p.get('drawing_number'), p.get('item_name'),
            p.get('revision'), p.get('quantity'), p.get('material'),
            p.get('project_number'), p.get('rfq_id'), p.get('rfq_code'), p.get('rfq_title'),
            p.get('rfq_status'), p.get('suppliers_count'), p.get('offers_count'),
            p.get('min_price'), p.get('invitations_sent'),
            p.get('viewers_count'), p.get('seen_item_count'), p.get('last_viewed_at'),
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
    args = parser.parse_args()

    try:
        agent = RMSyncAgent(args.master)
    except Exception as e:
        print(f'BLAD konfiguracji: {e}', file=sys.stderr)
        return 2

    exit_code = 0

    if args.full_state:
        try:
            print(f'Pelny stan pobrany: {agent.pull_full_state()} pozycji')
        except Exception as e:
            print(f'BLAD pobierania pelnego stanu: {e}', file=sys.stderr)
            exit_code = 1
        return exit_code

    if not args.results_only:
        try:
            print(f'Kooperanci wyslani: {agent.push_suppliers()}')
        except Exception as e:
            print(f'BLAD kanalu kooperantow: {e}', file=sys.stderr)
            exit_code = 1

    if not args.suppliers_only:
        try:
            print(f'Wyniki pobrane: {agent.pull_results()}')
        except Exception as e:
            print(f'BLAD kanalu wynikow: {e}', file=sys.stderr)
            exit_code = 1

        # aktywność kooperantów — osobno, bo błąd tutaj nie może wywalić
        # synchronizacji wyników (to dane pomocnicze do okna Wycena)
        try:
            print(f'Aktywnosc kooperantow: {agent.pull_activity()}')
        except Exception as e:
            print(f'BLAD kanalu aktywnosci: {e}', file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
