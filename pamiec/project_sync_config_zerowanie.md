---
name: project_sync_config_zerowanie
description: "sync_config.json zeruje sie przy ubiciu procesu — open(w) obcina plik PRZED zapisem; 9 miejsc, zapis takze w trakcie pracy; fix = os.replace"
metadata:
  node_type: memory
  type: project
---

**Zdarzylo sie 23.09.2026 (M-OLD).** `C:\RMPAK_CLIENT\sync_config.json`
mial **0 bajtow**. RM_BAZA nie wstawala:

```
Blad inicjalizacji
Expecting value: line 1 column 1 (char 0)
```

## Przyczyna: zapis NIE JEST atomowy

Wzorzec powtorzony w **9 miejscach** RM_BAZA_v15_MAG_STATS_ORG.py
(m.in. linie 4559, 4719, 5974, 33841, 34078, 34307, 34756, 34876, 36216):

```python
with open(CONFIG_FILE, 'w') as f:
    json.dump(config, f, indent=2)
```

`open(..., 'w')` **obcina plik do zera OD RAZU**, a tresc dopisuje dopiero
`json.dump`. Miedzy tymi krokami plik jest PUSTY. Proces ubity w tym oknie
zostawia 0 bajtow.

⚠️ **Zapis leci takze W TRAKCIE PRACY**, nie tylko przy zamykaniu:
ostatni uzytkownik po zalogowaniu, szerokosci kolumn, kolumny do druku,
ustawienia okna. Dlatego `Stop-Process -Force` moze trafic w to okno
w dowolnym momencie.

**Dlaczego nigdy wczesniej:** okno trafienia to ulamek sekundy. 23.09
aplikacja byla ubijana kilka razy pod rzad i w koncu trafilo.
To luka, ktora byla tam ZAWSZE — nie skutek zmian w kodzie.

## Skutek uboczny: gubi sie adres serwera

Po usunieciu pustego pliku `create_default_config()` odtwarza config
z **DEFAULT_RM_SERWER_HOST = "192.168.100.84"** — adres FIRMOWY.
W domu (M-OLD) ma byc `127.0.0.1:5060`, wiec RM_BAZA wisi na
`[WinError 10060]` i nie widzi mastera.

Ten sam blad opisuje komentarz w `rm_klient.py:66`:
„13.09.2026: agent RFQ na stacji domowej celowal w 192.168.100.84,
choc w sync_config.json stoi 127.0.0.1".

Gina tez: szerokosci kolumn, uklad okna, `last_user_id`,
`server_dir` (wraca na `Y:/SERVER_PROJEKTY` zamiast `V:/`).

## Naprawa doraźna (sprawdzona 23.09.2026)

1. skasowac pusty plik → aplikacja odtworzy go sama przy starcie;
2. **poprawic `rm_serwer.host` na `127.0.0.1`** (w domu);
3. sprawdzic „Serwer projekty" — ma byc `V:/`, nie `Y:/SERVER_PROJEKTY`;
4. ustawic na nowo szerokosci kolumn.

Kopie zapasowe configu sa STARE (luty/kwiecien) i maja sciezki na `Y:`
sprzed odciecia — **nie kopiowac ich wprost**, patrz [[project_odciecie_od_Y]].

## TODO: zapis atomowy (~15 linii)

Jedna funkcja pomocnicza zamiast 9 powtorzen:

```python
def zapisz_json_atomowo(sciezka, dane):
    tmp = str(sciezka) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dane, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())      # tresc na dysku PRZED podmiana
    if os.path.exists(sciezka):
        shutil.copy2(sciezka, str(sciezka) + ".bak")
    os.replace(tmp, sciezka)      # podmiana ATOMOWA
```

`os.replace` gwarantuje, ze plik jest albo STARY, albo NOWY — nigdy pusty.
Przy starcie: gdy config ma 0 bajtow lub nie parsuje sie, wziac `.bak`
zamiast od razu domyslnych (inaczej znow wejdzie adres firmowy).

Patrz [[project_srodowisko_domowe_m_old]] (host 127.0.0.1 w domu),
[[project_odciecie_od_Y]].
