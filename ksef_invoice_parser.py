"""
Parser faktur XML z KSeF (Krajowy System e-Faktur), schemat FA(2)/FA(3).

Faktury pobrane ręcznie z portalu KSeF w formacie XML mają wspólną strukturę
pozycji <FaWiersz> niezależnie od wariantu formularza (2 albo 3):
    P_7   - nazwa towaru/usługi
    P_8A  - jednostka miary
    P_8B  - ilość
    P_9A  - cena jednostkowa netto
    P_11  - wartość netto pozycji
    P_12  - stawka VAT

Elementy XML są w domyślnym namespace (zależnym od wersji schemy), więc
wyszukiwanie odbywa się po lokalnej nazwie tagu (bez namespace).
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class KsefInvoiceLine:
    nr_wiersza: int
    nazwa: str
    jednostka: str
    ilosc: float
    cena_netto: float
    wartosc_netto: float
    stawka_vat: str


@dataclass
class KsefInvoice:
    numer_faktury: str
    data_wystawienia: str
    sprzedawca_nazwa: str
    sprzedawca_nip: str
    nabywca_nazwa: str
    pozycje: list


def _local_tag(elem):
    tag = elem.tag
    return tag.split('}', 1)[1] if '}' in tag else tag


def _find_child_text(elem, local_name):
    for child in elem:
        if _local_tag(child) == local_name:
            return child.text
    return None


def _to_float(s):
    if s is None:
        return None
    s = str(s).strip().replace(',', '.')
    if s == '':
        return None
    return float(s)


def parse_ksef_invoice_xml(path):
    """
    Wczytuje plik XML faktury KSeF (FA(2) lub FA(3)) i zwraca KsefInvoice.
    Rzuca ValueError z czytelnym komunikatem, jeśli struktura się nie zgadza.
    """
    path = Path(path)
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise ValueError(f"Plik nie jest poprawnym XML-em:\n{e}")

    root = tree.getroot()
    if _local_tag(root) != 'Faktura':
        raise ValueError(
            f"To nie jest faktura KSeF — oczekiwano elementu <Faktura>, "
            f"znaleziono <{_local_tag(root)}>."
        )

    fa = None
    podmiot1 = None
    for child in root:
        lt = _local_tag(child)
        if lt == 'Fa':
            fa = child
        elif lt == 'Podmiot1':
            podmiot1 = child

    if fa is None:
        raise ValueError("Brak sekcji <Fa> w pliku — to nie jest poprawna faktura KSeF.")

    numer_faktury = _find_child_text(fa, 'P_2') or ''
    data_wystawienia = _find_child_text(fa, 'P_1') or ''

    sprzedawca_nazwa = ''
    sprzedawca_nip = ''
    if podmiot1 is not None:
        for child in podmiot1:
            if _local_tag(child) == 'DaneIdentyfikacyjne':
                sprzedawca_nazwa = _find_child_text(child, 'Nazwa') or ''
                sprzedawca_nip = _find_child_text(child, 'NIP') or ''

    pozycje = []
    for child in fa:
        if _local_tag(child) != 'FaWiersz':
            continue
        nr_str = _find_child_text(child, 'NrWierszaFa')
        nazwa = _find_child_text(child, 'P_7') or ''
        jednostka = _find_child_text(child, 'P_8A') or ''
        ilosc = _to_float(_find_child_text(child, 'P_8B'))
        cena_netto = _to_float(_find_child_text(child, 'P_9A'))
        wartosc_netto = _to_float(_find_child_text(child, 'P_11'))
        stawka_vat = _find_child_text(child, 'P_12') or ''

        pozycje.append(KsefInvoiceLine(
            nr_wiersza=int(nr_str) if nr_str else len(pozycje) + 1,
            nazwa=nazwa.strip(),
            jednostka=jednostka.strip(),
            ilosc=ilosc if ilosc is not None else 0.0,
            cena_netto=cena_netto if cena_netto is not None else 0.0,
            wartosc_netto=wartosc_netto if wartosc_netto is not None else 0.0,
            stawka_vat=stawka_vat.strip(),
        ))

    if not pozycje:
        raise ValueError("Faktura nie zawiera żadnych pozycji (<FaWiersz>).")

    return KsefInvoice(
        numer_faktury=numer_faktury,
        data_wystawienia=data_wystawienia,
        sprzedawca_nazwa=sprzedawca_nazwa,
        sprzedawca_nip=sprzedawca_nip,
        nabywca_nazwa='',
        pozycje=pozycje,
    )
