# ToSee-B Home Assistant — dokumentacja po polsku

**Drugie życie starego, bateryjnego wideodzwonka.**

ToSee-B Home Assistant to otwarty projekt badania protokołu komunikacyjnego
i integracji starszego wideodzwonka Wi-Fi z lokalnym środowiskiem
Home Assistant, bez polegania na funkcji zdalnego podglądu
oryginalnej aplikacji mobilnej ToSee.

**Status projektu: eksperymentalny.** Nie jest to jeszcze gotowa
integracja Home Assistant do instalacji jednym kliknięciem.

## Testowane urządzenie

![Wideodzwonek wykorzystany podczas prac](images/tosee-doorbell.jpg)

*Rzeczywisty dzwonek wykorzystany podczas tworzenia projektu.
Zdjęcie autora projektu.*

Urządzenie jest bateryjnym wideodzwonkiem Wi-Fi bez jednoznacznie
zidentyfikowanej marki i numeru modelu. Wcześniej współpracowało
ze starszą aplikacją ToSee, a parowanie odbywało się w trybie AP.

**Uwaga:** podobny wygląd innych dzwonków nie oznacza zgodności
protokołu ani oprogramowania.

## Dlaczego powstał ten projekt?

Dzwonek był sprawny, a aplikacja ToSee umożliwiała jego sparowanie
i podgląd wideo w domowej sieci LAN.

Problem pojawiał się podczas korzystania z transmisji danych
komórkowych. Aplikacja próbowała połączyć się z urządzeniem,
a niebieska dioda dzwonka migała, lecz obraz na żywo się nie pojawiał.

Początkowo podejrzewałem problem w konfiguracji swojej sieci,
szczególnie w firewallu pfSense. Po analizie nie udało mi się
jednak ustalić przyczyny problemu.

Zamiast wymieniać działające urządzenie, postanowiłem poznać
jego sposób komunikacji i samodzielnie zbadać protokół.

W ten sposób powstał projekt ToSee-B Home Assistant.

Dzięki wykorzystaniu mojego środowiska Home Assistant oraz jego
oddzielnie skonfigurowanego dostępu zdalnego mogę korzystać
z rozwiązania również spoza domowej sieci, bez polegania
na zdalnym podglądzie starej aplikacji ToSee.

**Dzwonek dostał drugie życie, a ja znacznie lepiej poznałem
zasady jego działania.**

Pełna historia projektu jest dostępna w
[głównym README](../README.md).

## Co już działa w testowanym środowisku?

- Odszyfrowywanie i analiza przechwyconych pakietów PPCS UDP.
- Rekonstrukcja obrazu H.264 z przechwyconych pakietów.
- Dekodowanie zapisanych plików PCAP i tworzenie nagrań MP4.
- Obsługa retransmisji i porządkowanie pakietów wideo.
- Wykrywanie aktywności dzwonka na podstawie zdarzeń sieciowych.
- Publikowanie zdarzeń przez MQTT.
- Przetwarzanie obrazu H.264 w rozdzielczości 1280 × 720.
- Przetwarzanie dźwięku G.711 A-law.
- Publikowanie transmisji audio/wideo przez RTSP z użyciem MediaMTX.
- Odtwarzanie strumienia RTSP w VLC.
- Uruchamianie sesji w odpowiedzi na wykrytą aktywność urządzenia.

## Co pozostaje do dopracowania?

- Niezawodne wyświetlanie transmisji przez Home Assistant/go2rtc.
- Uproszczona instalacja i konfiguracja dla innych użytkowników.
- Obsługa innych modeli i wersji oprogramowania urządzeń ToSee.
- Długoterminowa niezawodność połączeń i sesji.
- Kompletna natywna integracja z Home Assistant.

Projekt uwzględnia oszczędzanie energii przez bateryjny dzwonek.
Nie zakłada ciągłego, całodobowego strumieniowania obrazu.

## Jak działa obecne rozwiązanie?

1. Komputer z systemem Linux wykrywa zdarzenie związane z dzwonkiem.
2. Usługa publikuje odpowiednie powiadomienie MQTT.
3. W odpowiedzi na zdarzenie uruchamiana jest sesja komunikacji.
4. Obraz i dźwięk są przetwarzane i publikowane przez MediaMTX.
5. Strumień RTSP może zostać odtworzony przez zgodnego klienta.

Odtwarzanie RTSP zostało potwierdzone w VLC. Wyświetlanie
przez Home Assistant/go2rtc nadal wymaga dopracowania.

## Wymagania środowiska eksperymentalnego

- Linux, testowany na Debianie.
- Python 3 i środowisko wirtualne projektu.
- Narzędzia do analizy ruchu sieciowego, w tym TShark.
- FFmpeg do wybranych operacji multimedialnych.
- MediaMTX do udostępniania strumienia RTSP.
- Broker MQTT do obsługi zdarzeń.
- Odpowiednio skonfigurowana sieć lokalna.

Szczegółowa konfiguracja zależy od środowiska. Ten dokument
nie stanowi jeszcze uniwersalnego poradnika instalacyjnego.

## Testy

Z katalogu głównego repozytorium:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
```

Polecenie wymaga przygotowanego środowiska wirtualnego
i zależności projektu.
## Szczegółowa dokumentacja

Zobacz [ARCHITEKTURA_PL.md](ARCHITEKTURA_PL.md), aby poznać
architekturę, przepływ komunikacji, moduły projektu,
eksperymenty i ograniczenia techniczne.
## Ograniczenia

Projekt opracowano z wykorzystaniem jednego, konkretnego
egzemplarza wideodzwonka ToSee.

Zgodność z innymi urządzeniami nie została potwierdzona.
Straty pakietów, czas uruchamiania sesji i mechanizmy
oszczędzania baterii mogą wpływać na transmisję.

Nie ustalono jednoznacznie przyczyny problemów ze zdalnym
podglądem w oryginalnej aplikacji ToSee.
## Prywatność i bezpieczeństwo

Nie publikuj prywatnych przechwyceń PCAP, nagrań z kamery,
haseł, danych uwierzytelniających ani unikalnych
identyfikatorów urządzeń.

Nie udostępniaj niezabezpieczonych strumieni RTSP
bezpośrednio do internetu.
## Licencja

GNU General Public License v3.

Projekt wykorzystuje tablicę PPCS pochodzącą z projektu
cloudedge-client na licencji GPLv3.
Informacje o pochodzeniu znajdują się w [NOTICE.md](../NOTICE.md).
## Zastrzeżenie

To nieoficjalny projekt społecznościowy, niezwiązany
z producentem urządzenia ani twórcami aplikacji ToSee.

Korzystaj wyłącznie z własnych urządzeń i sieci
lub takich, do których masz odpowiednie uprawnienia.
