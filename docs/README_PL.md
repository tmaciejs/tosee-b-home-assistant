# ToSee-B Home Assistant — dokumentacja po polsku

Otwarty projekt obsługi bateryjnych wideodzwonków ToSee-B.

Celem projektu jest integracja z Home Assistant bez konieczności
utrzymywania stale podłączonego telefonu z Androidem.

## Co już działa?

- Odszyfrowywanie przechwyconych pakietów PPCS.
- Rekonstrukcja obrazu H.264.
- Automatyczna konwersja nagrań do MP4.
- Usuwanie retransmisji i porządkowanie pakietów.
- Obsługa częściowych strat pakietów.

Dekoder przetestowano na trzech niezależnych przechwyceniach
z jednego urządzenia ToSee-B.

Potwierdzona rozdzielczość obrazu: 1280 × 720.

## Co jeszcze nie działa?

- Samodzielne łączenie się z dzwonkiem bez Androida.
- Wybudzanie dzwonka z trybu oszczędzania baterii.
- Uruchamianie transmisji na żywo.
- Natywna integracja z Home Assistant.

**Obecna wersja dekoduje zapisane pliki PCAP.
Nie jest jeszcze integracją kamery na żywo.**

## Wymagania

- Linux
- Python 3
- TShark
- FFmpeg (do tworzenia MP4)

Instalacja w Debianie:

    sudo apt install python3 tshark ffmpeg

## Użycie

Odzyskanie obrazu H.264:

    python3 tosee_decode.py nagranie.pcap -o odzyskane.h264 --device-ip 192.0.2.10

Automatyczne utworzenie H.264 i MP4:

    python3 tosee_decode.py nagranie.pcap -o odzyskane.h264 --mp4 --fps 15 --device-ip 192.0.2.10

Adres IP należy zastąpić adresem własnego dzwonka.

Częstotliwość 15 FPS jest ustawieniem testowym.

## Testy

    python3 -m unittest discover -s tests -v

## Ograniczenia

Kompatybilność z innymi modelami i wersjami oprogramowania
nie została jeszcze potwierdzona.

Utrata pakietów może powodować uszkodzenia obrazu.

## Prywatność

Nie publikuj plików PCAP, prywatnych nagrań, haseł,
identyfikatorów urządzeń ani danych swojej sieci.

## Licencja

GNU General Public License v3.

Projekt wykorzystuje tablicę PPCS pochodzącą z projektu
cloudedge-client, udostępnionego na licencji GPL v3.
Przed publikacją należy uzupełnić informacje o autorach.

## Zastrzeżenie

Projekt nieoficjalny, niezwiązany z producentem urządzenia.
Korzystaj wyłącznie z własnych urządzeń i sieci lub takich,
do których masz odpowiednie uprawnienia.
