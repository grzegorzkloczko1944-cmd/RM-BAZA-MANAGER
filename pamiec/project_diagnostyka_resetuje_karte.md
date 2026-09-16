---
name: project_diagnostyka_resetuje_karte
description: "Zrywane połączenie: brama znika PIERWSZA, reset karty przez msdt to skutek nie przyczyna; objaw = błąd 85 i martwe dyski; przyczyna NIEUSTALONA (router/kabel)"
metadata:
  type: project
---

# Zrywane połączenie sieciowe — co WIEMY, a czego NIE

**16.09.2026, sprawa OTWARTA.** Połączenie pada co 2-3 minuty: dyski
`V:`/`B:`/`Y:` stają się martwe, dialog *„Przywracanie połączeń sieciowych —
Nazwa lokalnego urządzenia jest już w użyciu"* (błąd **85**), profil sieci
przeskakuje na „Prywatna". Kopiowanie 122 MB na `Y:` padało trzy razy z rzędu.

## Właściwa kolejność zdarzeń (dziennik System)

```
12:55:05  Diagnostics-Networking 4000
          Główna przyczyna: DOMYŚLNA BRAMA JEST NIEDOSTĘPNA   ← NAJPIERW
12:55:21  NetworkProfile 10001  Sieć odłączona
12:55:35  Diagnostics-Networking 5000
          Opcja naprawy: Zresetuj kartę sieciową „Ethernet"    ← DOPIERO POTEM
```

**Brama znika pierwsza.** Problem jest między stacją a routerem
(`192.168.100.1`), nie w samym Windows.

## ⚠️ Narzędzie diagnostyki POGŁĘBIA problem

Otwarty `msdt` („Rozwiązywanie problemów z siecią") resetuje kartę przy każdym
przebiegu — sześć razy w godzinę. Każdy reset zrywa sesje SMB i zajmuje literę
dysku, więc powstaje pętla: *dyski padają → user odpala diagnostykę → reset
karty → dyski padają*.

⛔ **Nie klikać „Zdiagnozuj i napraw problemy z siecią" przy tym objawie.**
Komunikat „Brama domyślna jest niedostępna — Naprawiony" jest MYLĄCY: opisuje
to, co narzędzie samo przed chwilą zrobiło, nie rozwiązanie.

⚠️ **Ale zamknięcie msdt NIE naprawia problemu** — rozłączenia trwają dalej
(sprawdzone: 12:55 przy zamkniętym narzędziu). To łagodzenie, nie naprawa.
Zaraz po zamknięciu udało się skopiować 122 MB na `Y:` w 2 s — okno spokoju
wystarczyło, żeby dokończyć wystawienie.

## Co WYKLUCZONE (nie powtarzać)

| Trop | Dlaczego odpada |
|---|---|
| karta / sterownik | `Get-NetAdapterStatistics`: **zero** błędów i odrzuconych pakietów, status `Up`, 2.5 Gbps |
| `backup_nic.bat` | chodzi na serwerze W2019S — osobna maszyna, osobne sesje SMB ([[project_backup_nic_poza_gitem]]) |
| poświadczenia SMB | to był INNY błąd — **1219**, 15.09 ([[project_nas_nic_poswiadczenia]]) |
| uśpienie komputera | realne i naprawione tego dnia, ale rozłączenia trwają przy PRACUJĄCYM komputerze ([[project_dyski_znikaja_uspienie]]) |
| Cloudflare WARP | zainstalowany 24.08.2026, bez konfiguracji firmowej, **zero tras** — ubicie klienta nie zatrzymało rozłączeń. Prawdopodobnie zbędny, ale nie sprawca |

## Co zostało do sprawdzenia

Brama w spokojnym momencie odpowiada **idealnie**: 30/30 pingów, śr. 19 ms,
ARP `Reachable`. Więc awaria jest przerywana. Dwaj kandydaci:

* **kabel / port w switchu** — wtedy przy zerwaniu `karta` zmieni się na
  `Disconnected`
* **router `192.168.100.1`** — wtedy `karta` zostanie `Up`, zniknie sama brama

**Rozstrzygnie to monitor** (scratchpad `monitor_sieci.ps1`) — loguje każdą
zmianę stanu do `%TEMP%\monitor_sieci.log`:

```
12:58:19  karta=Up link=2.5 Gbps ip=192.168.100.18 gw=192.168.100.1 ping=True Y=True
```

## How to apply

- ⚠️ `Test-Path Y:\` potrafi zwrócić **True przy martwej sesji** — litera
  istnieje, a zapis pada z „Nie można odnaleźć ścieżki sieciowej".
  **Testem jest ZAPIS, nie `Test-Path`.**
- Przy padniętym udziale serwera (`\\W2019S\RM_SERWER$`) logowanie kontem
  technicznym: `python -c "import udzial_serwera as u; u.zaloguj(cichy=False)"`.
  Odzyskuje dostęp bez restartu.
- Zatrzymanie usługi `CloudflareWARP` wymaga uprawnień administratora;
  ubicie procesu klienta — nie.
- Gdy trzeba coś wystawić przy szarpiącej sieci: zamknąć `msdt`, sprawdzić
  zapisem, kopiować od razu — okno spokoju bywa krótkie.
