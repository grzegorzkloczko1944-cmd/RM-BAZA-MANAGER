"""
Klient REST API KSeF 2.0 (Krajowy System e-Faktur) — uwierzytelnianie tokenem
KSeF, wyszukiwanie faktur zakupowych i pobieranie ich treści XML.

Oparte na oficjalnej dokumentacji CIRFMF (Ministerstwo Finansów):
    https://github.com/CIRFMF/ksef-docs

Flow uwierzytelniania tokenem (nie certyfikatem/XAdES):
    1. POST /auth/challenge                    -> challenge + timestamp (ważne 10 min)
    2. GET  /security/public-key-certificates  -> klucz publiczny MF do szyfrowania
    3. zaszyfruj "{token}|{timestampMs}" RSA-OAEP(SHA-256) kluczem publicznym MF, Base64
    4. POST /auth/ksef-token                   -> authenticationToken (tymczasowy) + referenceNumber
    5. GET  /auth/{referenceNumber}             -> poll aż status = uwierzytelniony
    6. POST /auth/token/redeem                  -> accessToken + refreshToken (właściwe)
    7. dalsze wywołania: nagłówek Authorization: Bearer {accessToken}
    8. DELETE /auth/sessions/current            -> zamknięcie sesji

Ten moduł NIE jest jeszcze wpięty do GUI RM_BAZA — to samodzielny klient API,
gotowy do użycia przez przyszły przycisk "Sprawdź nowe faktury KSEF".

ZASTRZEŻENIE — do zweryfikowania na środowisku testowym przed użyciem produkcyjnym:
    - Dokładny format odpowiedzi GET /invoices/ksef/{ksefNumber} (surowy XML czy
      JSON z polem base64) nie jest jednoznacznie potwierdzony w dostępnej
      dokumentacji opisowej — download_invoice_xml() zakłada surowy XML w body.
    - Dokładna struktura pól odpowiedzi /invoices/query/metadata (nazwy kluczy
      w JSON) jest odtworzona z przykładów SDK C#/Java, nie z surowego OpenAPI —
      przed produkcyjnym użyciem zweryfikuj w Swagger UI:
      https://api-test.ksef.mf.gov.pl/docs/v2/index.html
    - Endpoint zamknięcia sesji tokenowej (poza sesją interaktywną wysyłki
      faktur) może się różnić od DELETE /auth/sessions/current — do potwierdzenia.
"""

import base64
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

BASE_URL_TEST = "https://api-test.ksef.mf.gov.pl/v2"
BASE_URL_PRODUCTION = "https://api.ksef.mf.gov.pl/v2"


class KsefApiError(Exception):
    """Błąd komunikacji z API KSeF (HTTP != 2xx, timeout, niepoprawna odpowiedź)."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass
class KsefSession:
    access_token: str
    refresh_token: str
    reference_number: str
    base_url: str


@dataclass
class KsefInvoiceMetadata:
    ksef_number: str
    invoice_number: str
    seller_nip: str
    seller_name: str
    issue_date: str
    acquisition_date: str = ""


def _http_request(url, method="GET", body=None, headers=None, timeout=30):
    """Minimalny wrapper nad urllib — brak zależności od 'requests' w projekcie."""
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
        try:
            body_text = raw.decode("utf-8")
        except Exception:
            body_text = str(raw)
        raise KsefApiError(
            f"KSeF API {method} {url} -> HTTP {status}: {body_text}",
            status_code=status, response_body=body_text
        )
    except urllib.error.URLError as e:
        raise KsefApiError(f"KSeF API {method} {url} -> błąd połączenia: {e.reason}")

    if not raw:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return status, raw


def _encrypt_token_challenge(token, timestamp_ms, public_key_pem_or_der):
    """
    Szyfruje "{token}|{timestamp_ms}" RSA-OAEP(SHA-256, MGF1) kluczem publicznym MF.
    Zwraca Base64-encoded ciphertext (pole 'encryptedToken' w żądaniu /auth/ksef-token).
    """
    if not CRYPTO_AVAILABLE:
        raise KsefApiError(
            "Brak biblioteki 'cryptography' — wymagana do szyfrowania tokenu KSeF.\n"
            "Zainstaluj: pip install cryptography"
        )
    plaintext = f"{token}|{timestamp_ms}".encode("utf-8")
    try:
        public_key = serialization.load_der_public_key(public_key_pem_or_der)
    except Exception:
        public_key = serialization.load_pem_public_key(public_key_pem_or_der)

    ciphertext = public_key.encrypt(
        plaintext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("ascii")


def get_public_key_certificate(base_url):
    """
    GET /security/public-key-certificates -> pobiera pierwszy aktywny certyfikat
    (klucz publiczny MF do szyfrowania tokenu), zwraca surowe bajty DER.
    """
    status, resp = _http_request(f"{base_url}/security/public-key-certificates", method="GET")
    if not isinstance(resp, list) or not resp:
        raise KsefApiError("Brak certyfikatów publicznych w odpowiedzi KSeF.", status_code=status)
    # Bierzemy pierwszy wpis — API zwraca listę aktywnych certyfikatów, zwykle jeden wystarczy.
    cert_b64 = resp[0].get("certificate") or resp[0].get("publicKey")
    if not cert_b64:
        raise KsefApiError(f"Nieoczekiwany format odpowiedzi public-key-certificates: {resp[0]}")
    return base64.b64decode(cert_b64)


def authenticate_with_token(nip, ksef_token, base_url=BASE_URL_TEST, poll_interval_s=1.0, poll_timeout_s=30.0):
    """
    Pełny flow uwierzytelnienia tokenem KSeF. Zwraca KsefSession gotową do
    dalszych wywołań (query_invoices, download_invoice_xml).

    Args:
        nip: NIP firmy (kontekst uwierzytelnienia — musisz być nabywcą/podatnikiem tego NIP).
        ksef_token: token KSeF wygenerowany w aplikacji podatnika (Ustawienia -> Token API KSEF w RM_BAZA).
        base_url: BASE_URL_TEST (domyślnie) lub BASE_URL_PRODUCTION.
    """
    # 1. Challenge
    status, challenge_resp = _http_request(f"{base_url}/auth/challenge", method="POST", body={})
    challenge = challenge_resp.get("challenge")
    timestamp_str = challenge_resp.get("timestamp")
    if not challenge:
        raise KsefApiError(f"Brak 'challenge' w odpowiedzi /auth/challenge: {challenge_resp}")

    # Serwer zwraca timestamp ISO8601 — do szyfrowania trzeba znów w milisekundach epoch.
    try:
        ts_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        timestamp_ms = int(ts_dt.timestamp() * 1000)
    except Exception:
        timestamp_ms = int(time.time() * 1000)

    # 2. Klucz publiczny MF
    public_key_der = get_public_key_certificate(base_url)

    # 3. Szyfrowanie "{token}|{timestamp_ms}"
    encrypted_token = _encrypt_token_challenge(ksef_token, timestamp_ms, public_key_der)

    # 4. POST /auth/ksef-token
    auth_body = {
        "challenge": challenge,
        "contextIdentifier": {"type": "nip", "value": nip},
        "encryptedToken": encrypted_token,
    }
    status, auth_resp = _http_request(f"{base_url}/auth/ksef-token", method="POST", body=auth_body)
    temp_token = (auth_resp.get("authenticationToken") or {}).get("token")
    reference_number = auth_resp.get("referenceNumber")
    if not temp_token or not reference_number:
        raise KsefApiError(f"Nieoczekiwana odpowiedź /auth/ksef-token: {auth_resp}")

    # 5. Poll statusu uwierzytelnienia
    deadline = time.time() + poll_timeout_s
    auth_ok = False
    while time.time() < deadline:
        status, status_resp = _http_request(
            f"{base_url}/auth/{reference_number}", method="GET",
            headers={"Authorization": f"Bearer {temp_token}"}
        )
        status_code = (status_resp or {}).get("status", {}).get("code")
        if status_code == 200:
            auth_ok = True
            break
        if status_code and status_code >= 400:
            raise KsefApiError(f"Uwierzytelnienie KSeF nie powiodło się: {status_resp}")
        time.sleep(poll_interval_s)

    if not auth_ok:
        raise KsefApiError(f"Timeout oczekiwania na potwierdzenie uwierzytelnienia KSeF (referenceNumber={reference_number}).")

    # 6. Redeem -> właściwe accessToken/refreshToken
    status, redeem_resp = _http_request(
        f"{base_url}/auth/token/redeem", method="POST",
        headers={"Authorization": f"Bearer {temp_token}"}
    )
    access_token = (redeem_resp.get("accessToken") or {}).get("token") or redeem_resp.get("accessToken")
    refresh_token = (redeem_resp.get("refreshToken") or {}).get("token") or redeem_resp.get("refreshToken")
    if not access_token:
        raise KsefApiError(f"Nieoczekiwana odpowiedź /auth/token/redeem: {redeem_resp}")

    return KsefSession(
        access_token=access_token,
        refresh_token=refresh_token,
        reference_number=reference_number,
        base_url=base_url,
    )


def query_purchase_invoices(session, date_from, date_to, page_offset=0, page_size=50):
    """
    POST /invoices/query/metadata — lista faktur zakupowych (nasza firma = nabywca,
    Subject2 w metadanych KSeF — Subject1 to sprzedawca, Subject2 nabywca, zgodnie
    z FA(3): Podmiot1=sprzedawca, Podmiot2=nabywca) w zadanym zakresie dat wystawienia.

    Args:
        session: KsefSession z authenticate_with_token().
        date_from, date_to: daty w formacie ISO "YYYY-MM-DD".
        page_offset, page_size: paginacja.

    Returns:
        (list[KsefInvoiceMetadata], has_more: bool)
    """
    body = {
        "subjectType": "Subject2",  # nabywca (Subject1 = sprzedawca)
        "dateRange": {"dateType": "Issue", "from": date_from, "to": date_to},
    }
    url = f"{session.base_url}/invoices/query/metadata?pageOffset={page_offset}&pageSize={page_size}"
    status, resp = _http_request(
        url, method="POST", body=body,
        headers={"Authorization": f"Bearer {session.access_token}"}
    )
    items = resp.get("invoices", resp.get("items", []))
    results = []
    for it in items:
        results.append(KsefInvoiceMetadata(
            ksef_number=it.get("ksefNumber", ""),
            invoice_number=it.get("invoiceNumber", ""),
            seller_nip=(it.get("seller") or {}).get("nip", ""),
            seller_name=(it.get("seller") or {}).get("name", ""),
            issue_date=it.get("issueDate", ""),
            acquisition_date=it.get("acquisitionDate", ""),
        ))
    has_more = len(results) == page_size
    return results, has_more


def download_invoice_xml(session, ksef_number):
    """GET /invoices/ksef/{ksefNumber} — pobiera treść faktury jako surowy XML (bytes)."""
    url = f"{session.base_url}/invoices/ksef/{ksef_number}"
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {session.access_token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise KsefApiError(f"Nie udało się pobrać faktury {ksef_number}: HTTP {e.code}", status_code=e.code)
    except urllib.error.URLError as e:
        raise KsefApiError(f"Nie udało się pobrać faktury {ksef_number}: {e.reason}")


def close_session(session):
    """DELETE /auth/sessions/current — zamyka bieżącą sesję (unieważnia refreshToken)."""
    url = f"{session.base_url}/auth/sessions/current"
    req = urllib.request.Request(
        url, method="DELETE",
        headers={"Authorization": f"Bearer {session.access_token}"}
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as e:
        # Zamknięcie sesji nie jest krytyczne — token i tak wygaśnie samoistnie.
        print(f"⚠️  Nie udało się jawnie zamknąć sesji KSeF: HTTP {e.code}")
    except urllib.error.URLError as e:
        print(f"⚠️  Nie udało się jawnie zamknąć sesji KSeF: {e.reason}")
