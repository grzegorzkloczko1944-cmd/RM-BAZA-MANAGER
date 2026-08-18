"""
Ekstrakcja miniatury rysunku z pliku DWF + cache na dysku.

DWF = ZIP z 12-bajtowym prefiksem "(DWF V06.20)". W sekcji ePlot (arkusz
rysunku) Autodesk zapisuje gotowy podglad PNG ~320x180, oznaczony
role="thumbnail" w descriptor.xml. Zero zaleznosci od Inventora / Windows
Shell - sam zipfile + Pillow.

Skopiowane z RM_DWF (repo NOW) - moduł samodzielny, zależy tylko od Pillow.
"""
import hashlib
import io
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageChops

THUMB_CACHE_DIR = Path(__file__).parent / '.dwf_thumb_cache'

_THUMBNAIL_RE = re.compile(r'role="thumbnail"[^>]*href="([^"]+)"')

# Autodesk renderuje caly arkusz w stalej skali - maly detal zostawia duzy
# szary margines, przez co rysunek wyglada malenko obok innych. Przycinamy
# margines do tresci i centrujemy ja w kwadratowej miniaturze.
# Zrodlowy PNG z DWF jest maly (~348x180, tresc po cropie czesto ~80-150px).
# Nieograniczony upscale (do THUMB_SIZE) robil z cienkich linii grube,
# pikselowe "karykatury" - stad MAX_UPSCALE: powiekszamy najwyzej Nx, reszta
# zostaje wysrodkowana z marginesem zamiast rozciagana dalej. Idealny
# wektorowy rendering (.w2d) wymagalby DWF Toolkit - odrzucone (cel projektu:
# zero zaleznosci natywnych).
CROP_MARGIN = 8          # zapas px wokol tresci, zeby nie uciac rysunku na styk
THUMB_SIZE = 360         # bok docelowego kwadratu
MAX_UPSCALE = 2.0        # limit powiekszenia tresci ponad jej naturalny rozmiar
THUMB_BG = (232, 228, 216)  # kremowe tlo arkusza (#e8e4d8) - spojne z CSS karty


def extract_thumb(dwf_path):
    """Zwraca (PIL.Image, info) miniatury arkusza rysunku z DWF, albo (None, powod)."""
    try:
        raw = Path(dwf_path).read_bytes()
    except OSError as e:
        return None, f'blad odczytu pliku: {e}'

    pk = raw.find(b'PK\x03\x04')
    if pk < 0:
        return None, 'brak kontenera ZIP w pliku DWF'

    try:
        z = zipfile.ZipFile(io.BytesIO(raw[pk:]))
    except zipfile.BadZipFile as e:
        return None, f'uszkodzony ZIP: {e}'

    names = z.namelist()

    # 1) ePlot descriptor -> ImageResource role="thumbnail" (miniatura arkusza rysunku)
    for n in names:
        if n.lower().endswith('descriptor.xml') and 'eplot' in n.lower():
            try:
                d = z.read(n).decode('utf-8', 'replace')
            except Exception:
                continue
            m = _THUMBNAIL_RE.search(d)
            if m:
                href = m.group(1).replace('\\', '/')
                if href in names:
                    try:
                        return Image.open(io.BytesIO(z.read(href))), 'ePlot thumbnail'
                    except Exception as e:
                        return None, f'blad dekodowania PNG: {e}'

    # 2) fallback: najwiekszy PNG w sekcji ePlot
    eplot_png = [
        (z.getinfo(n).file_size, n) for n in names
        if 'eplot' in n.lower() and n.lower().endswith('.png')
    ]
    if eplot_png:
        _, n = max(eplot_png)
        try:
            return Image.open(io.BytesIO(z.read(n))), 'ePlot max-png (fallback)'
        except Exception as e:
            return None, f'blad dekodowania PNG: {e}'

    # 3) fallback: podglad modelu 3D (eModel jpg) - dla plikow bez arkusza rysunku
    for n in names:
        if 'emodel' in n.lower() and n.lower().endswith('.jpg'):
            try:
                return Image.open(io.BytesIO(z.read(n))), 'eModel jpg (3D fallback)'
            except Exception as e:
                return None, f'blad dekodowania JPG: {e}'

    return None, 'brak podgladu w pliku DWF'


def _render_enhanced(im):
    """Przycina margines wokol rysunku i centruje tresc w kwadrat THUMB_SIZE.
    Skaluje w dol bez ograniczen, ale w gore najwyzej MAX_UPSCALE razy -
    zapobiega to rozciaganiu bardzo malych rysunkow do pikselowej karykatury
    (patrz komentarz przy stalych powyzej)."""
    im = im.convert('RGB')

    # 1) przytnij jednolity margines (tlo = piksel w rogu 0,0)
    bg = im.getpixel((0, 0))
    diff = ImageChops.difference(im, Image.new('RGB', im.size, bg))
    bbox = diff.getbbox()
    if bbox:
        left, top, right, bottom = bbox
        left = max(0, left - CROP_MARGIN)
        top = max(0, top - CROP_MARGIN)
        right = min(im.width, right + CROP_MARGIN)
        bottom = min(im.height, bottom + CROP_MARGIN)
        im = im.crop((left, top, right, bottom))

    # 2) wpasuj tresc w kwadrat THUMB_SIZE, zachowujac proporcje.
    #    W dol bez limitu, w gore najwyzej MAX_UPSCALE.
    ratio = min(THUMB_SIZE / im.width, THUMB_SIZE / im.height, MAX_UPSCALE)
    new_size = (max(1, round(im.width * ratio)), max(1, round(im.height * ratio)))
    resized = im.resize(new_size, Image.LANCZOS) if ratio != 1.0 else im

    canvas = Image.new('RGB', (THUMB_SIZE, THUMB_SIZE), THUMB_BG)
    offset = ((THUMB_SIZE - new_size[0]) // 2, (THUMB_SIZE - new_size[1]) // 2)
    canvas.paste(resized, offset)
    return canvas


def _render_raw(im):
    """Surowy arkusz z DWF bez zadnej obrobki (bez crop, bez skalowania) -
    dokladnie to co plik daje z automatu. Tylko konwersja do RGB pod PNG."""
    return im.convert('RGB')


_RENDERERS = {
    'enhanced': _render_enhanced,
    'raw': _render_raw,
}


def _cache_key(dwf_path, mode):
    try:
        mtime = Path(dwf_path).stat().st_mtime
    except OSError:
        mtime = 0
    raw_key = f'{dwf_path}|{mtime}|{mode}'
    return hashlib.md5(raw_key.encode('utf-8')).hexdigest()


def get_cached_thumb_path(dwf_path, mode='enhanced'):
    """Zwraca Path do PNG miniatury w cache, generujac ja przy pierwszym zadaniu.
    mode: 'enhanced' (crop + ograniczony upscale, domyslny) albo 'raw' (surowy
    arkusz bez obrobki). Kazdy tryb ma wlasny klucz cache - oba warianty
    wspolistnieja na dysku niezaleznie. Klucz = hash(sciezka+mtime+mode) -
    zmiana pliku na serwerze automatycznie uniewaznia stary cache.
    Zwraca None, gdy DWF nie ma podgladu."""
    renderer = _RENDERERS.get(mode, _render_enhanced)

    THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(dwf_path, mode)
    cache_path = THUMB_CACHE_DIR / f'{key}.png'
    if cache_path.exists():
        return cache_path

    im, _info = extract_thumb(dwf_path)
    if im is None:
        return None

    renderer(im).save(cache_path, 'PNG')
    return cache_path
