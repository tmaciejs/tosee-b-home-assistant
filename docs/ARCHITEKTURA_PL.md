# Architektura projektu ToSee-B Home Assistant

> Dokumentacja techniczna i edukacyjna w języku polskim.
>
> Projekt: `tmaciejs/tosee-b-home-assistant`
>
> Stan początkowy dokumentacji: 26 października 2026 r.
>
> Ten dokument jest rozwijany na podstawie rzeczywistego kodu
> projektu. Opisuje architekturę działającej wersji v14.
> Fragmenty wymagające dalszej analizy są wyraźnie oznaczone.

---

## 1. Dla kogo jest ten dokument?

Dokument powstał z myślą o osobach zainteresowanych automatyką
domową, Home Assistant, systemem Linux i programowaniem Python.

Nie trzeba być doświadczonym programistą, aby z niego korzystać.

Celem jest wyjaśnienie:

- za co odpowiada każdy moduł projektu;
- dlaczego poszczególne pliki są potrzebne;
- jak programy wymieniają między sobą informacje;
- które elementy pracują stale, a które tylko po zdarzeniu;
- jak analizować problemy bez zakłócania działania kamery;
- jak uruchamiać testy i rozwijać kod.

W przykładach rozróżniamy kod Python, polecenia systemu Linux,
usługi systemd i zewnętrzne procesy.

---

## 2. Co robi projekt?

ToSee-B Home Assistant umożliwia wykorzystanie kamerowego
dzwonka ToSee-B w lokalnym systemie automatyki domowej.

Najważniejsze zadania:

1. Wykrywanie naciśnięcia przycisku dzwonka.
2. Wykrywanie zdarzenia ruchu.
3. Publikowanie tych zdarzeń przez MQTT.
4. Uruchamianie połączenia z kamerą tylko wtedy, gdy jest potrzebne.
5. Odbieranie obrazu H.264 i dźwięku G.711 A-law.
6. Udostępnianie transmisji przez MediaMTX w protokole RTSP.
7. Umożliwienie odtwarzania transmisji w Home Assistant.

Ważnym założeniem jest oszczędzanie akumulatora kamery.
Sam nasłuch zdarzeń nie wymaga stale aktywnej sesji P2P.

Projekt nie wymaga ciągłego nagrywania obrazu.

---

## 3. Architektura systemu

### 3.1. Wykrywanie zdarzeń

```text
Kamera ToSee-B
  |
  | pakiety UDP
  v
Router pfSense
  |
  | tcpdump uruchomiony przez SSH
  v
event_listener.py
  |
  | obiekt Event
  v
event_service.py
  |
  +----> mqtt_events.py ----> broker MQTT ----> Home Assistant
  |
  +----> wątek tosee-video
             |
             v
        av_publisher_v14.py
             |
             v
          MediaMTX
             |
             v
       RTSP / Home Assistant
```
MediaMTX może utrzymywać obraz zastępczy
STREAM IS OFFLINE, kiedy kamera nie nadaje.

Zaobserwowano, że VLC poprawnie przechodzi z obrazu
zastępczego na LIVE. Obsługa takiego przejścia przez
Home Assistant/go2rtc pozostaje przedmiotem diagnostyki.

## 4. Usługi działające w tle
### 4.1. tosee-b.service
Plik konfiguracji:

/etc/systemd/system/tosee-b.service

Uruchamiany moduł:

src/tosee_b/event_service.py

Usługa korzysta z interpretera Python znajdującego się
w środowisku .venv i działa jako użytkownik tosee.

Plik konfiguracyjny jest przekazywany argumentem:

--env-file /home/tosee/.tosee.env

Zadania usługi:
- utrzymywanie nasłuchu zdarzeń;
- publikowanie MQTT;
- rozpoczynanie sesji wideo po zdarzeniu;
- obsługa błędów uruchamiania transmisji.
Jest to główny proces aplikacji.
### 4.2. mediamtx.service
Plik konfiguracji:

/etc/systemd/system/mediamtx.service

Program:

/usr/local/bin/mediamtx

Konfiguracja:

/etc/mediamtx/mediamtx.yml

MediaMTX odbiera publikowany strumień RTSP i udostępnia
go odbiornikom, np. VLC lub Home Assistant.

Ścieżka używana przez aktualny publikator:

rtsp://127.0.0.1:8554/tosee-av-test

Adres 127.0.0.1 oznacza lokalny komputer Debian.
### 4.3. Co działa jako osobny proces?
Należy odróżniać:
- Moduł Python: plik .py, który można importować.
- Proces: uruchomiony program w systemie operacyjnym.
- Wątek: część procesu wykonująca zadanie równolegle.
- Usługa systemd: sposób zarządzania procesem w Linuxie.
event_listener.py nie jest osobną usługą systemd.

Jego funkcja listen_events() działa w procesie Python
uruchomionym przez tosee-b.service.

Jednak listen_events() uruchamia zewnętrzny proces SSH,
a SSH uruchamia tcpdump na pfSense.

W razie zdarzenia event_service.py może uruchomić
osobny wątek o nazwie tosee-video.


## 5. Szczegółowy opis event_listener.py
Ścieżka:

src/tosee_b/event_listener.py
### 5.1. Główne zadanie
Moduł obserwuje ruch sieciowy dzwonka ToSee-B za
pośrednictwem routera pfSense.

Nie wymaga w tym celu aktywnej sesji strumieniowania P2P.
### 5.2. Jakie pakiety rozpoznaje?
Aktualny kod rozpoznaje:
| Długość UDP raportowana przez tcpdump | Zdarzenie |
|---|---|
| 1052 bajty | `motion` — wykrycie ruchu |
| 1104 bajty | `doorbell` — naciśnięcie przycisku |

Dodatkowo sprawdzane są:
- adres źródłowy kamery: 192.168.1.138;
- port docelowy: 15000 albo 25000;
- protokół UDP.
Te wartości ustalono dla konkretnego środowiska.
Nie należy zakładać, że są uniwersalne dla każdej kamery.
### 5.3. PACKET_RE
PACKET_RE jest wyrażeniem regularnym.

Jest to wzorzec używany do odnajdywania określonych
fragmentów w tekście wyświetlanym przez tcpdump.

Jeżeli linia nie odpowiada wzorcowi, jest ignorowana.
### 5.4. EVENT_BY_LENGTH
Słownik Python przyporządkowujący rozmiar pakietu
do rodzaju zdarzenia.

Przykład:

EVENT_BY_LENGTH = {
    1052: "motion",
    1104: "doorbell",
}

### 5.5. Klasa Event
```python
@dataclass(frozen=True)
class Event:
    kind: str
    timestamp: float
```



Obiekt przechowuje:
- kind — rodzaj zdarzenia;
- timestamp — czas wykrycia uzyskany z zegara monotonicznego.
frozen=True zapobiega zwykłej modyfikacji pól obiektu
po jego utworzeniu.
### 5.6. Funkcja parse_packet()
Analizuje pojedynczą linię tekstu z tcpdump.

Zwraca:
- "motion" dla rozpoznanego ruchu;
- "doorbell" dla rozpoznanego przycisku;
- None dla nierozpoznanej linii.
### 5.7. Klasa EventDeduplicator
Kamera może wysłać kilka pakietów dla jednego zdarzenia.

Deduplikacja zapobiega wielokrotnemu zgłaszaniu
tego samego zdarzenia w krótkim czasie.

Domyślny odstęp wynosi 3 sekundy.

Zdarzenia motion i doorbell są śledzone oddzielnie.

Do odmierzania czasu używany jest time.monotonic(),
który nie zależy od ręcznych zmian zegara systemowego.
### 5.8. Funkcja listen_events()
Jest to generator Python, z którego korzysta
event_service.py.

Domyślne parametry:
- SSH: admin@192.168.1.1;
- interfejs pfSense: igc1;
- opcjonalny callback: on_event.

Funkcja:
1. Buduje polecenie tcpdump.
2. Uruchamia SSH w trybie bez interaktywnego pytania o hasło.
3. Korzysta z pseudoterminala PTY.
4. Odczytuje kolejne fragmenty wyjścia tcpdump.
5. Dzieli tekst na wiersze.
6. Wywołuje parse_packet().
7. Odrzuca duplikaty.
8. Tworzy obiekt Event.
9. Przekazuje zdarzenie instrukcją yield event.
Zdalny tcpdump jest uruchamiany przez timeout 60.
Po prawidłowym zakończeniu pętla zestawia nową sesję.

Obsługa zakończenia sprząta również proces SSH.
### 5.9. Co oznacza yield?
yield przekazuje wynik wywołującemu kodowi, ale
pozwala później kontynuować działanie generatora.

Właśnie dlatego event_service.py może wykonywać:
```python
for event in listen_events():
    print(event.kind)
```



i otrzymywać kolejne zdarzenia bez ponownego
ręcznego uruchamiania funkcji.

## 6. Szczegółowy opis event_service.py
Ścieżka:

src/tosee_b/event_service.py

Jest to aktualny punkt wejścia usługi systemd.
### 6.1. Importowane moduły projektu
```python
from .event_listener import listen_events
from .mqtt_events import publish_event
from .av_publisher_v14 import publish_av_session
from .runner import load_config
```



Każdy import dostarcza inne zadanie:
- listen_events — odbiera zdarzenia;
- publish_event — publikuje MQTT;
- publish_av_session — uruchamia transmisję audio/wideo;
- load_config — przygotowuje konfigurację klienta kamery.
### 6.2. Funkcja load_env_file()
Odczytuje plik konfiguracyjny w formie tekstowej.

Każda linia w formacie KLUCZ=WARTOSC staje się
elementem słownika Python.

Puste linie i komentarze zaczynające się od #
są pomijane.

Istotne: plik nie jest wykonywany jako kod powłoki.
### 6.3. Funkcja main()
To główna funkcja uruchamiająca usługę.

Najpierw odczytuje argument --env-file,
następnie przygotowuje słownik ustawień i blokadę.

Dalej wchodzi w pętlę:

for event in listen_events():

Po otrzymaniu zdarzenia:
1. Wypisuje WYKRYTO.
2. Wywołuje publish_event().
3. Wypisuje MQTT_WYSLANO.
4. Próbuje uruchomić sesję wideo.
### 6.4. Po co threading.Lock()?
video_lock = threading.Lock()



Blokada zabezpiecza przed jednoczesnym
uruchomieniem dwóch transmisji.

Jeżeli kamera już transmituje, kolejne zdarzenie
nie tworzy drugiej sesji.

Program zapisuje wówczas:

TOSEE_VIDEO_ALREADY_RUNNING

MQTT dla tego zdarzenia jest jednak nadal publikowane.
### 6.5. Funkcja run_video()
Jest funkcją wewnętrzną zdefiniowaną w main().

Odpowiada za:
- pobranie konfiguracji kamery;
- uruchomienie publish_av_session();
- zapis statystyk lub błędów;
- zwolnienie blokady w sekcji finally.
Aktualna długość sesji to 120 sekund.
### 6.6. Osobny wątek transmisji

threading.Thread(
    target=run_video,
    daemon=True,
    name="tosee-video",
).start()


Transmisja działa w osobnym wątku.

Główny wątek może dzięki temu nadal nasłuchiwać
kolejnych zdarzeń.

Wątek daemon=True nie blokuje zakończenia
całego procesu Python.
### 6.7. Kolejność MQTT i wideo
MQTT jest publikowane przed rozpoczęciem transmisji.

Dlatego Home Assistant może otrzymać informację
o dzwonku wcześniej niż pojawi się obraz LIVE.

To zachowanie wynika bezpośrednio z kolejności
instrukcji w event_service.py.
### 6.8. Ważna uwaga konfiguracyjna
W kodzie istnieje historyczna domyślna ścieżka
DEFAULT_ENV_FILE, związana ze środowiskiem
deweloperskim.

Usługa systemd przekazuje jednak własny argument:

--env-file /home/tosee/.tosee.env

To właśnie ta ścieżka obowiązuje na serwerze produkcyjnym.

## 7. Który plik przeczytać jako pierwszy?
Osobie początkującej proponujemy kolejność:
1. event_service.py — główna logika programu.
2. event_listener.py — skąd pochodzą zdarzenia.
3. mqtt_events.py — przekazywanie zdarzeń do HA.
4. runner.py — konfiguracja połączenia z kamerą.
5. av_publisher_v14.py — transmisja audio i wideo.
6. live.py — odbiór danych z kamery.
7. video.py i audio.py — analiza mediów.
8. transport.py, session.py, crypto.py —
   komunikacja niskopoziomowa.
Czytanie projektu w tej kolejności pozwala zrozumieć
najpierw ogólny przepływ informacji, a dopiero później
szczegóły protokołów.

## 8. Bezpieczna diagnostyka

Poniższe polecenia pozwalają sprawdzić stan systemu
bez zatrzymywania usług i bez inicjowania sesji kamery.

### 8.1. Status głównej usługi

```bash
systemctl status tosee-b.service --no-pager
```

### 8.2. Status MediaMTX

```bash
systemctl status mediamtx.service --no-pager
```

### 8.3. Ostatnie komunikaty usługi

```bash
journalctl -u tosee-b.service -n 50 --no-pager
```

Przed udostępnieniem logów należy sprawdzić,
czy nie zawierają prywatnych identyfikatorów
lub innych danych wrażliwych.

### 8.4. Testy automatyczne

Uruchamiane z katalogu projektu jako użytkownik `tosee`:

```bash
cd /home/tosee/tosee-b-home-assistant
PYTHONPATH=src .venv/bin/python -m unittest discover \
    -s tests -p 'test_*.py' -q
```

Potwierdzony wynik:

```text
Ran 159 tests in 3.799s

OK
```

Więcej informacji zawiera rozdział 31.

Testy nie zastępują weryfikacji działania
całego systemu na rzeczywistym sprzęcie.

## 9. Kopie bezpieczeństwa

Na serwerze przygotowano skrypt:

```text
/usr/local/sbin/tosee-create-backup.sh
```

Tworzy archiwum projektu, przekazuje je do TrueNAS
i uruchamia kontrolę integralności kopii.

Miejsce przechowywania lokalnego:

```text
/home/tosee/backups/
```

Lokalizacja zdalna w analizowanym środowisku:

```text
//192.168.1.117/SERVER/HA/
```

Archiwa mogą zawierać hasła i dane prywatne.
Nie należy dodawać ich do publicznego repozytorium GitHub.

GitHub przechowuje kod źródłowy i historię jego zmian,
natomiast archiwa są kopiami działającego środowiska.

## 10. Mapa modułów i rozdziałów dokumentacji

Poniższa tabela ułatwia odnalezienie opisu
poszczególnych części programu.

| Moduł lub obszar | Rozdział |
|---|---|
| `event_listener.py` | 5 |
| `event_service.py` | 6 |
| `mqtt_events.py` | 13 |
| `runner.py` | 14 |
| `av_publisher_v14.py` | 15 |
| `live.py` | 16 |
| `video.py` | 17 |
| `video_reorder.py` | 18 |
| `audio.py` | 19 |
| `drw.py` | 20 |
| `ack.py` | 21 |
| `commands.py` | 22 |
| `session.py` | 23 |
| `crypto.py` | 24 |
| `punch.py` | 25 |
| `transport.py` | 26 |
| `reconnect.py` | 27 |
| `publisher.py` | 28 |
| `av_publisher.py` i warianty historyczne | 29 |
| `event_service_v14.py` | 30 |
| Testy automatyczne | 31 |

Wersje historyczne publikatorów opisano zbiorczo,
z uwzględnieniem najważniejszych zmian pomiędzy nimi.

Dalszego rozwinięcia mogą wymagać między innymi
instrukcja odtwarzania systemu z kopii,
słowniczek pojęć i szczegółowa diagnostyka
integracji Home Assistant/go2rtc.

## 11. Bezpieczeństwo i prywatność
Dokumentacja przeznaczona do GitHub nie powinna
zawierać prawdziwych haseł, tokenów, kluczy prywatnych
ani identyfikatorów poufnych urządzenia.

Przed publikacją należy sprawdzić każdy nowy plik.

Nie należy publikować przechwyconych danych .pcap,
plików .env, prywatnych archiwów i nagrań.

## 12. Status dokumentacji

Dokument zawiera 31 rozdziałów obejmujących
architekturę, usługi, moduły Pythona,
historię publikatorów oraz testy automatyczne.

Potwierdzono pomyślne wykonanie 159 testów.

Dokumentacja opisuje stan projektu analizowany
26 października 2026 r.

Podgląd LIVE w Home Assistant/go2rtc nadal wymaga
dalszej diagnostyki przełączania ze strumienia
zastępczego na rzeczywistą transmisję.

Przed publikacją dokument podlega kontroli
formatowania, poprawności technicznej
oraz danych wrażliwych.

---

## 13. Moduł mqtt_events.py — komunikacja z Home Assistant

**Ścieżka:** `src/tosee_b/mqtt_events.py`

### 13.1. Do czego służy?

Moduł publikuje informacje o zdarzeniach kamery w brokerze MQTT.

MQTT to protokół wymiany wiadomości. Nadawca publikuje wiadomość
na określony temat (*topic*), a odbiorca może subskrybować ten temat.

Dzięki temu kod obsługujący kamerę nie musi komunikować się
bezpośrednio z Home Assistant.

### 13.2. Kto wywołuje moduł?

Aktualna usługa `event_service.py` wywołuje:

```python
publish_event(event.kind, environ=settings)
```

event.kind pochodzi z obiektu utworzonego w event_listener.py.
Może mieć wartość motion albo doorbell.
### 13.3. Słownik TOPICS
```python
TOPICS = {
    "motion": "tosee_b/event/motion",
    "doorbell": "tosee_b/event/doorbell",
}
```



Słownik wiąże wewnętrzną nazwę zdarzenia z tematem MQTT.
| Zdarzenie | Temat MQTT | Treść |
|---|---|---|
| Ruch | `tosee_b/event/motion` | `ON` |
| Dzwonek | `tosee_b/event/doorbell` | `ON` |

### 13.4. Funkcja publish_event(kind, environ=None)
Argumenty:
- kind — rodzaj zdarzenia: motion lub doorbell;
- environ — opcjonalny słownik z ustawieniami MQTT.
Jeżeli environ nie zostanie przekazany, funkcja używa os.environ.

Wymagane ustawienia:
- TOSEE_MQTT_HOST — adres brokera MQTT;
- TOSEE_MQTT_USERNAME — nazwa użytkownika;
- TOSEE_MQTT_PASSWORD — hasło.
Ustawienie opcjonalne:

- TOSEE_MQTT_PORT — port brokera, domyślnie 1883.

Nie należy umieszczać prawdziwych haseł w dokumentacji
ani w kodzie przesyłanym do GitHub.
### 13.5. Kolejność działania
1. Funkcja sprawdza, czy rozpoznaje podany rodzaj zdarzenia.
2. Sprawdza wymagane ustawienia MQTT.
3. Tworzy klienta biblioteki paho-mqtt.
4. Konfiguruje nazwę użytkownika i hasło.
5. Rejestruje funkcję zwrotną on_connect().
6. Łączy się z brokerem i uruchamia pętlę sieciową.
7. Czeka na potwierdzenie połączenia, maksymalnie 5 sekund.
8. Publikuje wiadomość ON.
9. Czeka na potwierdzenie publikacji, maksymalnie 5 sekund.
10. Zamyka połączenie i zatrzymuje pętlę sieciową.
### 13.6. Czym jest callback on_connect()?
Callback to funkcja uruchamiana przez bibliotekę po zajściu
określonego zdarzenia.

Tutaj on_connect() otrzymuje informację o wyniku połączenia
z brokerem MQTT i sygnalizuje ją przez threading.Event.

threading.Event nie jest tym samym co klasa Event
z pliku event_listener.py.

Pierwszy obiekt służy do synchronizacji wątków.
Drugi przechowuje informację o zdarzeniu kamery.
### 13.7. Dlaczego qos=1 i retain=False?
```python
client.publish(
    TOPICS[kind],
    payload="ON",
    qos=1,
    retain=False,
)
```



- qos=1 oznacza poziom dostarczenia MQTT „co najmniej raz”.
  W wyjątkowych sytuacjach wiadomość może zostać dostarczona
  ponownie, dlatego nie należy zakładać dokładnie jednego odbioru.
- retain=False oznacza, że broker nie zapisuje wiadomości jako
  zapamiętanego ostatniego stanu tematu.
- Funkcja nie wysyła komunikatu OFF.
Sposób prezentacji krótkiego impulsu zdarzenia zależy również
od konfiguracji Home Assistant.
### 13.8. Obsługa błędów
Możliwe błędy obejmują:
- nieznany rodzaj zdarzenia — ValueError;
- brak ustawień MQTT — ValueError;
- brak potwierdzenia połączenia — TimeoutError;
- odrzucenie połączenia — RuntimeError;
- brak potwierdzenia publikacji — TimeoutError;
- błąd publikacji — RuntimeError.
Instrukcja finally próbuje rozłączyć klienta i zatrzymać
jego pętlę sieciową również w przypadku wyjątku.
### 13.9. Co warto zapamiętać?
Ten moduł nie wykrywa ruchu, nie odbiera obrazu i nie steruje
kamerą. Ma jedno główne zadanie: przekazać gotowe zdarzenie
do MQTT i sprawdzić wynik publikacji.

## 14. Moduł runner.py — konfiguracja i starszy cykl sesji
Ścieżka: src/tosee_b/runner.py
### 14.1. Do czego służy?
Moduł odpowiada za:
1. Odczytywanie i sprawdzanie ustawień połączenia z kamerą.
2. Zarządzanie kolejnymi sesjami starszego publikatora RTSP.
Aktualna usługa event_service.py wykorzystuje z tego pliku
funkcję load_config(), ale nie wywołuje run_forever().

To ważne, ponieważ w projekcie zachowano zarówno starszą
ścieżkę publikowania, jak i aktualny publikator v14.
### 14.2. Klasa RunnerConfig
```python
@dataclass(frozen=True)
class RunnerConfig:
    address: tuple[str, int]
    did: bytes
    client_uuid: str
    rtsp_url: str
```



@dataclass pomaga utworzyć klasę przechowującą dane.
- address — para (adres IP lub host, port UDP);
- did — identyfikator urządzenia zapisany jako bajty;
- client_uuid — identyfikator klienta w postaci tekstowej;
- rtsp_url — docelowy adres publikacji RTSP.
frozen=True oznacza, że pól nie można zwyczajnie
nadpisywać po utworzeniu obiektu.
### 14.3. Funkcja load_config(environ=None)
Wejście: słownik ustawień lub zmienne środowiskowe.

Wyjście: obiekt RunnerConfig.

Wymagane nazwy ustawień:
- TOSEE_HOST;
- TOSEE_DID_HEX;
- TOSEE_CLIENT_UUID.
Opcjonalne:
- TOSEE_PORT, domyślnie 10000;
- TOSEE_RTSP_URL, domyślnie
  rtsp://127.0.0.1:8554/tosee.
Funkcja używa bytes.fromhex(), aby zamienić zapis
szesnastkowy DID na dane binarne.

DID musi mieć dokładnie 20 bajtów.

Port UDP musi mieścić się w zakresie od 1 do 65535.

Przykładowy schemat użycia, bez prawdziwych identyfikatorów:
```python
config = load_config(settings)
print(config.address)
```



### 14.4. Jak korzysta z tego event_service.py?
config = load_config(settings)



Zwrócony obiekt jest następnie używany przy uruchamianiu
aktualnej sesji v14:
```python
publish_av_session(
    address=config.address,
    did=config.did,
    client_uuid=config.client_uuid,
    rtsp_url="rtsp://127.0.0.1:8554/tosee-av-test",
    duration=120.0,
)
```



Ważne: w tej ścieżce aktualna usługa podaje własny adres RTSP.
Dlatego domyślny rtsp_url z RunnerConfig nie określa
adresu aktualnej transmisji v14.
### 14.5. Funkcja run_forever()
Ta funkcja zarządza kolejnymi sesjami starszego publikatora.

Argumenty:
- config — ustawienia typu RunnerConfig;
- should_stop — funkcja informująca, czy zakończyć pracę;
- retry_delay — odstęp ponowienia, domyślnie 3 sekundy;
- session_duration — czas sesji, domyślnie 3600 sekund.
Parametry czasu są sprawdzane przed rozpoczęciem pracy.
### 14.6. Jedno gniazdo UDP
```python
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind(("0.0.0.0", 0))
```



- AF_INET oznacza IPv4.
- SOCK_DGRAM oznacza gniazdo datagramowe, używane przez UDP.
- 0.0.0.0 oznacza nasłuchiwanie na lokalnych interfejsach.
- Port 0 oznacza wybór wolnego portu lokalnego przez system.
Gniazdo jest współdzielone przez kolejne sesje
uruchamiane wewnątrz tej funkcji.
### 14.7. Zmiana portu po udanej sesji
W słowniku state zapisywane są:
```python
state = {
    "next_port": config.address[1],
    "failed": False,
}
```



Po poprawnym zakończeniu publish_session() wartość
next_port jest zwiększana o 1.

Jeżeli sesja zgłosi jeden z obsługiwanych wyjątków,
ustawiane jest failed=True.
### 14.8. Dlaczego program zatrzymuje próby po błędzie?
Komentarz w kodzie wskazuje powód: ochrona kamery
akumulatorowej, która może przejść w stan uśpienia.

Nie chcemy wielokrotnie wysyłać żądań PUNCH
do urządzenia, które w danej chwili nie odpowiada.

guarded_stop() łączy wewnętrzną informację o błędzie
z funkcją should_stop() przekazaną przez wywołującego.
### 14.9. Funkcja session_factory()
Tworzy prosty obiekt SimpleNamespace, udostępniający
metodę run wskazującą na wewnętrzną funkcję run_session.

Jest to adapter między lokalną logiką sesji a modułem
reconnect.py.

run_with_reconnect() otrzymuje fabrykę sesji,
warunek zakończenia i odstęp ponawiania.

Szczegółowe działanie ponawiania połączeń opisujemy
dopiero po analizie kodu reconnect.py.
### 14.10. Zależności modułu
```text
runner.py
  |
  +-- load_config() --> RunnerConfig
  |
  +-- run_forever()
        |
        +-- publisher.py: publish_session()
        |
        +-- reconnect.py: run_with_reconnect()
```


W aktualnej usłudze v14 wykorzystywana jest pierwsza
część tego modułu, czyli load_config().
### 14.11. Co warto zapamiętać?
runner.py jest dobrym przykładem pliku, który ma
więcej niż jedną odpowiedzialność.

Samo importowanie load_config() nie uruchamia
run_forever() ani starszego publikatora.

Dzięki temu możemy wykorzystywać sprawdzony mechanizm
konfiguracji w nowszym kodzie, nie uruchamiając
historycznej ścieżki transmisji.


---

## 15. Moduł av_publisher_v14.py — transmisja obrazu i dźwięku

**Plik:** `src/tosee_b/av_publisher_v14.py`

**Rola:** odbieranie mediów z kamery przez `ToSeeBLive`, łączenie
obrazu i dźwięku w kontenerze NUT oraz publikowanie RTSP przez FFmpeg.

Jest to publikator wykorzystywany przez aktualny `event_service.py`.

### 15.1. Schemat przepływu danych

```text
Kamera ToSee-B
       |
       | pakiety UDP
       v
SafeToSeeBLive
       |
       +--- on_h264(data) ---+
       |                    |
       +--- on_audio(data) --+
                            |
                            v
                  submit(kind, data)
                            |
                            v
                   queue.Queue(512)
                            |
                            v
                  mux_worker() / PyAV
                            |
                            | kontener NUT
                            v
                        Sink.write()
                            |
                            | pipe:0
                            v
                          FFmpeg
                            |
                            | RTSP przez TCP
                            v
                         MediaMTX
```

Funkcja `publish_av_session()` zarządza całym cyklem,
od rozpoczęcia połączenia aż po zamknięcie procesów.

### 15.2. Klasa SafeToSeeBLive

```python
class SafeToSeeBLive(ToSeeBLive):
```

To przykład **dziedziczenia** w Pythonie.

`SafeToSeeBLive` korzysta z funkcjonalności klasy `ToSeeBLive`
z modułu `live.py`, ale zmienia zachowanie metody `_receive()`.

W szczególności przechwytuje dwa błędy:

- `Invalid ToSee-B audio payload size`
- `Invalid ToSee-B audio frame header`

Dla tych dwóch przypadków wypisuje komunikat
`AUDIO_INVALID_PACKET_SKIPPED` i zwraca `None`.

Pozostałe wyjątki typu `ValueError` są zgłaszane dalej.

Dlaczego to ważne? Pojedynczy błędny pakiet audio
nie musi kończyć całej sesji transmisji.

Sposób interpretowania wartości `None` należy analizować
w połączeniu z kodem klasy bazowej `ToSeeBLive`.

### 15.3. Funkcja publish_av_session()

Argumenty funkcji:

| Argument | Znaczenie |
|---|---|
| `address` | Adres IP i port UDP kamery |
| `did` | Binarny identyfikator urządzenia |
| `client_uuid` | Identyfikator klienta |
| `rtsp_url` | Adres publikowanej transmisji RTSP |
| `duration` | Maksymalny czas sesji przekazywany do klienta |
| `bind_address` | Lokalny adres powiązania gniazda UDP |

Domyślny adres RTSP w tym module to:

`rtsp://127.0.0.1:8554/tosee-av-test`

Domyślny czas sesji samej funkcji wynosi 60 sekund.

Aktualny `event_service.py` przekazuje jednak
`duration=120.0`, czyli 120 sekund.

Funkcja odrzuca czas `duration` mniejszy lub równy zeru.

### 15.4. Biblioteki wykorzystane w module

Najważniejsze zależności:

- `socket` — tworzenie lokalnego gniazda UDP.
- `subprocess` — uruchomienie procesu FFmpeg.
- `threading` — osobny wątek multipleksowania i sygnał końca.
- `queue` — bezpieczne przekazywanie danych między wątkami.
- `time` — pomiar czasu i tworzenie znaczników czasowych.
- `os` — zapis bajtów do potoku FFmpeg.
- `av` (PyAV) — tworzenie kontenera NUT i pakietów mediów.
- `fractions.Fraction` — dokładne reprezentowanie podstawy czasu.
- `live.ToSeeBLive` — właściwa komunikacja z kamerą.
- `video.h264_nal_types` — rozpoznawanie typów jednostek H.264.

Część importów znajduje się na początku pliku, a część
wewnątrz `publish_av_session()`.

### 15.5. Kolejka pakietów

```python
packets = queue.Queue(maxsize=512)
errors = queue.Queue()
stop = threading.Event()
```

`packets` przechowuje dane przeznaczone do multipleksowania.

Maksymalna pojemność wynosi 512 elementów.

`errors` przekazuje wyjątki z wątku multipleksera
do głównej części funkcji.

`stop` jest sygnałem pozwalającym zakończyć pracę
wątku po odebraniu ostatnich pakietów z kolejki.

Kolejka jest bezpieczna dla współpracujących wątków.

### 15.6. Jak uruchamiany jest FFmpeg?

FFmpeg startuje przez `subprocess.Popen()`.

Przyjmuje kontener NUT ze standardowego wejścia:

```text
-f nut -i pipe:0
```

Publikuje oba strumienie w RTSP:

```text
-map 0:v:0
-map 0:a:0
-c:v copy
-c:a copy
-f rtsp
-rtsp_transport tcp
```

`copy` oznacza przekazanie skompresowanych danych bez
ponownego kodowania przez FFmpeg.

Nie oznacza to jednak, że nie ma żadnego przetwarzania:
PyAV tworzy pakiety i multipleksuje je wcześniej do NUT.

### 15.7. Po co klasa Sink?

Wewnątrz `publish_av_session()` zdefiniowano klasę `Sink`.

Jej metoda `write(data)` przesyła bajty do standardowego
wejścia FFmpeg za pomocą `os.write()`.

Potok jest ustawiony w tryb nieblokujący:

```python
os.set_blocking(ffmpeg.stdin.fileno(), False)
```

Jeżeli FFmpeg chwilowo nie nadąża z odbieraniem danych,
może pojawić się `BlockingIOError`.

W takim przypadku `Sink.write()`:

1. Sprawdza, czy FFmpeg nadal działa.
2. Sprawdza limit czasu.
3. Czeka 10 milisekund.
4. Ponawia zapis pozostałych bajtów.

Jeżeli zapis nie powiedzie się w ciągu 3 sekund,
zgłaszany jest `TimeoutError("NUT pipe blocked")`.

Takie ograniczenie chroni program przed niekończącym się
oczekiwaniem na niedostępny proces FFmpeg.

### 15.8. Czym jest kontener NUT?

NUT to format kontenera multimedialnego.

Pozwala przekazywać obraz i dźwięk w jednym strumieniu,
wraz z informacjami o kolejności i czasie pakietów.

W tym projekcie:

- Python odbiera osobne dane audio i wideo.
- PyAV tworzy strumienie i przypisuje pakietom znaczniki czasu.
- NUT przenosi oba strumienie do FFmpeg.
- FFmpeg publikuje je przez RTSP.

NUT jest tutaj formatem pośrednim, a nie formatem nagrania
zapisywanego na dysku.

### 15.9. Parametry obrazu i dźwięku

Konfiguracja strumienia wideo:

| Parametr | Wartość |
|---|---|
| Kodek | H.264 |
| Szerokość | 1280 pikseli |
| Wysokość | 720 pikseli |
| Deklarowana częstotliwość | 20 klatek/s |
| Podstawa czasu pakietów | 1/90000 |

Konfiguracja audio:

| Parametr | Wartość |
|---|---|
| Kodek | G.711 A-law (`pcm_alaw`) |
| Częstotliwość próbkowania | 8000 Hz |
| Liczba kanałów | 1 (mono) |
| Podstawa czasu pakietów | 1/8000 |

Są to parametry ustawiane przez kod publikatora.
Rzeczywistą liczbę odebranych klatek można sprawdzić
w statystykach transmisji.

### 15.10. Co oznaczają PTS i DTS?

**PTS (Presentation Timestamp)** wskazuje czas prezentacji
danych odbiorcy.

**DTS (Decoding Timestamp)** wskazuje czas dekodowania.

W aktualnej implementacji dla obu rodzajów pakietów
przypisywane są identyczne wartości PTS i DTS.

Dla wideo znacznik czasu powstaje z różnicy między
czasem odebrania pakietu a początkiem sesji:

```python
pts = round((timestamp - started) * 90000)
```

Kod pilnuje również, aby kolejne znaczniki wideo
były ściśle rosnące.

Dla audio stosowana jest skala 8000 jednostek
na sekundę i zwiększanie licznika o `len(data)`.

Dla ośmiobitowego mono G.711 A-law oznacza to
postęp odpowiadający liczbie próbek w pakiecie.

### 15.11. Korekta synchronizacji audio: -300 ms

Wersja v14 zawiera:

```python
audio_offset_ms = -300
audio_offset_pts = round(audio_offset_ms * 8)
```

Ponieważ zegar audio używa 8000 jednostek na sekundę,
jedna milisekunda odpowiada 8 jednostkom.

Stąd:

```text
-300 ms * 8 = -2400 jednostek PTS
```

Ta wartość jest dodawana do PTS/DTS pakietów audio.

Ważne: nie usuwa się przez to 300 ms próbek i nie
przyspiesza nagrania. Zmienia się sposób oznaczenia
czasowego danych przekazywanych do multipleksera.

Jest to ustawienie konkretnej działającej wersji v14,
a nie uniwersalna wartość dla wszystkich urządzeń.

### 15.12. Wątek mux_worker()

Funkcja `mux_worker()` działa w osobnym wątku o nazwie:

`tosee-nut-mux`

Jej zadania:

1. Otwiera wyjście PyAV w formacie NUT.
2. Tworzy strumień obrazu H.264.
3. Tworzy strumień dźwięku G.711 A-law.
4. Odbiera elementy z kolejki `packets`.
5. Oblicza znaczniki czasu.
6. Tworzy obiekty `av.Packet`.
7. Przypisuje pakiety do odpowiednich strumieni.
8. Wysyła pakiety przez `output.mux(pkt)`.
9. Zwiększa liczniki `counts`.

Dla wideo wykorzystywana jest funkcja
`h264_nal_types(data)`.

Jeżeli w pakiecie występuje jednostka NAL typu 5,
pakiet jest oznaczany jako klatka kluczowa.

Wyjątki z wątku są przekazywane do kolejki `errors`.

### 15.13. Funkcje submit(), on_h264() i on_audio()

`on_h264(data)` i `on_audio(data)` są funkcjami zwrotnymi,
które przekazujemy do obiektu `SafeToSeeBLive`.

Obie wywołują `submit()`, podając rodzaj danych.

`submit()`:

- sprawdza zgłoszone błędy multipleksera;
- sprawdza, czy proces FFmpeg nadal działa;
- kopiuje dane do obiektu `bytes`;
- zapisuje monotoniczny czas odebrania;
- próbuje wstawić pakiet do kolejki bez oczekiwania.

Gdy kolejka jest pełna, zgłasza:

`RuntimeError("NUT packet queue full")`

W ten sposób moduł nie pozwala kolejce rosnąć bez końca.

### 15.14. Odbieranie mediów z kamery

Program tworzy lokalne gniazdo UDP:

```python
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind((bind_address, 0))
```

Port `0` pozwala systemowi przydzielić wolny port lokalny.

Następnie tworzy klienta:

```python
client = SafeToSeeBLive(
    sock=sock,
    address=address,
    did=did,
    client_uuid=client_uuid,
    on_h264=on_h264,
    on_audio=on_audio,
)
```

Główna sesja jest uruchamiana przez:

```python
stats = client.run(duration=duration)
```

Szczegółowy przebieg wymiany pakietów z kamerą
opisujemy w rozdziale dotyczącym `live.py`.

### 15.15. Zamykanie i sprzątanie zasobów

Blok `finally` wykonuje czynności porządkujące
również wtedy, gdy wystąpi wyjątek.

Najpierw:

```python
stop.set()
worker.join(timeout=10)
```

Program sygnalizuje koniec pracy i daje wątkowi
multipleksera czas na zakończenie.

Jeżeli wątek nadal działa:

- zabija proces FFmpeg;
- ponownie czeka na wątek;
- zapisuje błąd zablokowanego multipleksera.

Następnie zamyka `ffmpeg.stdin`.

Program czeka maksymalnie 10 sekund na FFmpeg.
Jeżeli ten nie kończy pracy, wywołuje `ffmpeg.kill()`.

Po zakończeniu sprzątania sprawdza:

- czy wystąpił błąd multipleksera;
- czy FFmpeg zwrócił kod zakończenia różny od zera.

Dopiero po tych kontrolach zwraca `stats`.

### 15.16. Statystyki i komunikaty diagnostyczne

Moduł utrzymuje liczniki:

```python
counts = {"video": 0, "audio": 0}
```

Są one zwiększane po wykonaniu `output.mux(pkt)`.

Przy pierwszym pakiecie każdego rodzaju wypisywany jest
komunikat `V13_FIRST_MUX`.

Na końcu poprawnej sesji pojawia się:

`V13_MUX_COUNTS`

Mimo przedrostka `V13` są to komunikaty znajdujące się
w kodzie wersji v14. Nie dowodzą użycia starszego modułu.

`stats` są natomiast zwracane z `client.run()`.

Szczegółową zawartość tych statystyk ustalimy podczas
analizy `live.py`.

### 15.17. Czego ten moduł nie robi?

`av_publisher_v14.py` nie:

- wykrywa naciśnięć dzwonka przez pfSense;
- publikuje wiadomości MQTT;
- konfiguruje encji Home Assistant;
- uruchamia usługi systemd;
- zapisuje automatycznie nagrań na dysk.

Jego odpowiedzialnością jest pojedyncza sesja
transmisji audio/wideo do wskazanego serwera RTSP.

### 15.18. Najważniejsza zależność

```text
event_service.py
    |
    +-- runner.load_config()
    |
    +-- av_publisher_v14.publish_av_session()
            |
            +-- live.ToSeeBLive
            +-- video.h264_nal_types
            +-- PyAV / NUT
            +-- FFmpeg
                    |
                    v
                 MediaMTX
```

Zrozumienie tego schematu pozwala odróżnić
odbieranie danych od kamery od ich publikowania.

**Następny moduł do przeanalizowania: `live.py`.**
Opisze on właściwy mechanizm komunikacji i odbioru
pakietów z kamery.


---

## 16. Moduł live.py — komunikacja z kamerą ToSee-B

**Plik:** `src/tosee_b/live.py`

**Główna klasa:** `ToSeeBLive`

**Rola:** zarządzanie pojedynczą sesją komunikacji UDP z kamerą,
odbieranie pakietów DRW, składanie obrazu H.264 i przekazywanie audio.

To jeden z najważniejszych modułów całego projektu.

### 16.1. Miejsce w architekturze

```text
event_service.py
        |
        v
av_publisher_v14.py
        |
        v
SafeToSeeBLive
        |
        v
ToSeeBLive (live.py)
        |
        +-- transport.py ------> PUNCH
        +-- commands.py -------> Komendy sterujące
        +-- session.py --------> Inicjalizacja i ACK
        +-- drw.py ------------> Analiza pakietów DRW
        +-- ack.py ------------> Potwierdzanie pakietów
        +-- video_reorder.py --> Kolejność pakietów wideo
        +-- video.py ----------> Parsowanie i synchronizacja H.264
        +-- audio.py ----------> Wyodrębnianie G.711 A-law
        +-- crypto.py ---------> Szyfrowanie komunikatu zamknięcia
```

Moduł `live.py` nie publikuje samodzielnie RTSP.

Zamiast tego wywołuje funkcje zwrotne dostarczone
przez wyższy poziom aplikacji.

### 16.2. Czym jest klasa ToSeeBLive?

```python
class ToSeeBLive:
    """Run one bounded ToSee-B LAN video session."""
```

Klasa gromadzi w jednym obiekcie wszystkie informacje
niezbędne do przeprowadzenia jednej sesji z kamerą.

Jej konstruktor przyjmuje:

| Argument | Znaczenie |
|---|---|
| `sock` | Gniazdo UDP utworzone przez wywołującego |
| `address` | Adres i port kamery |
| `did` | Identyfikator urządzenia |
| `client_uuid` | Identyfikator klienta |
| `on_h264` | Callback odbierający obraz |
| `on_audio` | Opcjonalny callback odbierający dźwięk |

Przykładowy fragment z wersji v14:

```python
client = SafeToSeeBLive(
    sock=sock,
    address=address,
    did=did,
    client_uuid=client_uuid,
    on_h264=on_h264,
    on_audio=on_audio,
)
```

`SafeToSeeBLive` dziedziczy po `ToSeeBLive` i zmienia
zachowanie przy dwóch rozpoznanych błędach audio.

### 16.3. Klasa LiveStats

```python
@dataclass
class LiveStats:
    video_packets: int = 0
    audio_packets: int = 0
    video_blocks: int = 0
    output_blocks: int = 0
    output_bytes: int = 0
```

Wszystkie pola początkowo mają wartość zero.

| Pole | Co jest liczone |
|---|---|
| `video_packets` | Odebrane pakiety DRW kanału wideo |
| `audio_packets` | Odebrane pakiety DRW kanału audio |
| `video_blocks` | Klatki zwrócone przez parser wideo |
| `output_blocks` | Bloki H.264 zaakceptowane przez synchronizator |
| `output_bytes` | Łączna długość przekazanych danych H.264 |

Statystyki aktualizowane są w `_receive()`.

`run()` zwraca obiekt `LiveStats`.

Nie należy utożsamiać `video_packets` z liczbą gotowych
klatek przekazanych do FFmpeg. Jedna klatka może wymagać
złożenia danych z więcej niż jednego pakietu.

### 16.4. Elementy przygotowywane w __init__()

Konstruktor tworzy m.in.:

```python
self.parser = VideoFrameParser()
self.reorder = VideoReorderBuffer(window_size=128)
self.sync = H264Sync()
self.stats = LiveStats()
```

Ich role:

- `parser` — przetwarza fragmenty danych wideo.
- `reorder` — porządkuje je według sekwencji.
- `sync` — kontroluje gotowość strumienia H.264.
- `stats` — zbiera liczniki.

Program przechowuje też informacje o ostatnim pakiecie,
wykrytej luce i konieczności odzyskania synchronizacji.

### 16.5. Dlaczego pakiety wideo mają numery sekwencyjne?

UDP nie gwarantuje dostarczenia wszystkich pakietów ani
zachowania ich kolejności.

Kamera przesyła pakiety DRW z numerem sekwencyjnym.

Kod wykorzystuje ten numer, aby rozpoznawać sytuacje,
w których pakiet dotarł poza kolejnością albo zaginął.

Numer jest interpretowany w zakresie 16-bitowym.

Wyrażenie:

```python
(sequence + 1) & 0xFFFF
```

pozwala obsłużyć przejście z `65535` z powrotem do `0`.

### 16.6. Metoda _receive(timeout)

To podstawowa metoda odbierająca pakiety.

W uproszczeniu wykonuje następujące czynności:

1. Ustawia czas oczekiwania na gnieździe UDP.
2. Odbiera datagram przez `recvfrom()`.
3. Sprawdza adres nadawcy.
4. Próbuje rozpoznać pakiet DRW.
5. W razie potrzeby wysyła potwierdzenie ACK.
6. Rozdziela obsługę kanału wideo i audio.
7. Aktualizuje odpowiednie statystyki.
8. Wywołuje callbacki dla gotowych mediów.

Nie każdy odebrany datagram jest pakietem wideo.

Niektóre datagramy należą do komunikacji sterującej
i są później analizowane przez `_exchange()`.

Jeśli wystąpi `socket.timeout`, metoda sprawdza
stan luki wideo i zwraca `None`.

Pakiety z nieoczekiwanego adresu nadawcy są ignorowane.

### 16.7. Kanały DRW

Kod rozpoznaje następujące kanały:

| Kanał | Zastosowanie w live.py |
|---|---|
| `0` | Komunikacja sterująca |
| `1` | Dane obrazu |
| `2` | Dane dźwięku |

Dla poprawnie sparsowanych pakietów tych trzech kanałów
program wysyła ACK:

```python
self.sock.sendto(
    build_drw_ack(channel, [sequence]),
    self.address,
)
```

ACK jest potwierdzeniem odbioru pakietu.

Nie oznacza samo w sobie, że obraz został już
prawidłowo złożony albo wyświetlony.

### 16.8. Odbieranie wideo

Dla kanału `1` program:

1. Zwiększa `video_packets`.
2. Sprawdza ciągłość kolejnych numerów pakietów.
3. Rejestruje ostrzeżenie przy nieoczekiwanej sekwencji.
4. Przekazuje pakiet do `VideoReorderBuffer`.
5. Przetwarza dane we właściwej kolejności.
6. Przekazuje je do `VideoFrameParser`.
7. Sprawdza wynik przez `H264Sync`.
8. Wywołuje `on_h264(h264)` dla zaakceptowanego bloku.

Dopiero na końcu tego łańcucha dane opuszczają `live.py`
i trafiają do publikatora.

### 16.9. Bufor zmiany kolejności pakietów

```python
self.reorder = VideoReorderBuffer(window_size=128)
```

Bufor ma skonfigurowane okno 128 numerów sekwencyjnych.

Szczegółowe zasady przechowywania, odrzucania i wydawania
pakietów znajdują się w `video_reorder.py`.

W `live.py` widzimy natomiast, że rezultat `push()`
jest przetwarzany jako uporządkowana lista fragmentów.

### 16.10. Mechanizm wykrywania luki

Czas oczekiwania wynosi:

```python
self._video_gap_timeout = 0.250
```

Oznacza to 250 milisekund.

Metoda `_check_video_gap_timeout(now)` sprawdza,
czy bufor nadal oczekuje na brakujący pakiet.

Jeśli luka trwa zbyt długo, program wypisuje:

`TOSEE_VIDEO_GAP_TIMEOUT`

Następnie:

1. Wybiera punkt wznowienia na podstawie oczekujących
   numerów sekwencyjnych w buforze.
2. Odrzuca stan luki.
3. Ustawia nowy oczekiwany numer sekwencyjny.
4. Resetuje parser obrazu.
5. Resetuje synchronizator H.264.
6. Włącza tryb odzyskiwania synchronizacji.

Kod wybierający punkt wznowienia opiera się na
16-bitowej arytmetyce numerów sekwencyjnych.

To mechanizm awaryjny: może wiązać się z pominięciem
części danych, aby uniknąć utrzymywania uszkodzonego
stanu strumienia.

### 16.11. Odzyskiwanie synchronizacji H.264

Po wykrytej luce ustawiane jest:

```python
self._video_resync_needed = True
```

Następne uporządkowane fragmenty danych są kierowane do:

```python
self.parser.feed_keyframe_resync(ordered_payload)
```

Jeżeli funkcja nie zwróci klatek, program nadal czeka
na możliwość odzyskania synchronizacji.

Gdy pojawią się klatki, flaga jest wyłączana.

Program wykonuje dodatkowo `self.parser.feed(b"")`,
aby odebrać dane gotowe do przetworzenia po resynchronizacji.

To ważny mechanizm, ale nie gwarantuje odzyskania
każdej utraconej klatki. Jego ograniczenia powinny
być analizowane razem z kodem i testami `video.py`.

### 16.12. Odbieranie audio

Dla kanału `2` kod zwiększa `audio_packets`.

Jeżeli dostarczono callback audio, wykonuje:

```python
self.on_audio(extract_alaw(payload))
```

Funkcja `extract_alaw()` pochodzi z `audio.py`.

Jej zadaniem jest wydobycie właściwych danych audio
z ładunku pakietu DRW.

Dokładny układ nagłówków audio zostanie opisany
w rozdziale poświęconym `audio.py`.

### 16.13. Metoda _valid_response(sequence, payload)

To metoda pomocnicza sprawdzająca odpowiedzi sterujące.

Reguły wynikające z kodu:

| Sekwencja | Oczekiwana odpowiedź |
|---|---|
| `0` | 12 zerowych bajtów |
| `1` | Obiekt JSON zawierający klucz `sw_ver` |
| `2` | Trzy liczby 32-bitowe: `0, 0, 5` |
| `3` | Trzy liczby 32-bitowe: `0, 0, 3` |

Dla sekwencji `1` parser próbuje interpretować JSON
od przesunięć 0, 4, 8 oraz 12 bajtów.

Nieznane sekwencje nie przechodzą walidacji.

### 16.14. Metoda _exchange()

Metoda wysyła pojedyncze polecenie sterujące
i oczekuje poprawnej wymiany z kamerą.

Parametry:

```python
_exchange(sequence, packet, timeout=4.0, retries=3)
```

Domyślnie:

- całkowity limit czasu wynosi 4 sekundy;
- program podejmuje maksymalnie 3 wysłania;
- kolejne wysłanie może nastąpić po 0,8 sekundy;
- odbieranie w pętli korzysta z krótkich limitów czasu.

Warunkiem sukcesu są jednocześnie:

1. Potwierdzenie DRW ACK dla właściwej sekwencji.
2. Odpowiedź sterująca, która przechodzi `_valid_response()`.

W przeciwnym razie zgłaszany jest `TimeoutError`.

Sama obecność ACK nie wystarcza do uznania
całego polecenia za zakończone sukcesem.

### 16.15. Metoda run(duration)

To główna metoda obsługująca sesję.

Jej przebieg:

```text
Sprawdzenie duration
        |
        v
perform_punch()
        |
        v
Wymiana sterująca nr 0
        |
        v
Wymiana sterująca nr 1
        |
        v
Wymiana sterująca nr 2
        |
        v
Wymiana sterująca nr 3
        |
        v
Początek odliczania duration
        |
        v
Pętla odbioru UDP
        |
        v
Zwrócenie LiveStats
        |
        v
finally: zamknięcie sesji
```

W rzeczywistym wykonaniu blok `finally` realizowany jest
przed oddaniem wyniku do kodu wywołującego.

`duration` obejmuje fazę odbioru mediów po zakończeniu
inicjalizacji, a nie czas całej procedury PUNCH i sterowania.

### 16.16. Czym jest PUNCH?

Kod rozpoczyna komunikację przez:

```python
perform_punch(self.sock, self.address, self.did)
```

Funkcja pochodzi z `transport.py`.

Jeżeli nie potwierdzi sukcesu, sesja kończy się wyjątkiem:

`TimeoutError("ToSee-B PUNCH failed")`

W `live.py` nie implementujemy szczegółów PUNCH.
Odpowiada za nie niższa warstwa projektu.

### 16.17. Cztery polecenia inicjalizacji

W metodzie `run()` budowana jest sekwencja:

```python
commands = (
    (0, build_init_drw_packet(self.client_uuid)),
    (1, build_drw_packet(1, 1)),
    (2, build_drw_packet(2, 5)),
    (3, build_drw_packet(3, 3)),
)
```

Każdy element zawiera numer sekwencyjny i gotowy pakiet.

Następnie program wykonuje `_exchange()` dla każdego
elementu, zachowując kolejność.

Dopiero po czterech udanych wymianach rozpoczyna
właściwą fazę transmisji.

### 16.18. Metoda _close_session()

Zamknięcie używa komunikatu:

```python
closing = bytes.fromhex("f1f00000")
```

Program szyfruje go przez `encrypt_packet()`
i wysyła do kamery.

Następnie czeka na odpowiedź maksymalnie 0,5 sekundy.

Odebrany datagram zostaje odszyfrowany.
Jeżeli wynik odpowiada komunikatowi zamknięcia,
metoda zwraca `True`.

Gdy odpowiedź nie nadejdzie albo nastąpi obsługiwany
błąd systemowy, metoda zwraca `False`.

Wartość ta jest wynikiem próby potwierdzenia zamknięcia,
a nie informacją o liczbie odebranych klatek.

### 16.19. Dlaczego stosujemy try/finally?

W metodzie `run()` wykorzystywany jest blok `finally`.

Jeśli PUNCH się powiódł, `_close_session()` zostaje wywołana
również przy błędzie późniejszej inicjalizacji lub odbioru.

To pomaga zakończyć sesję protokołu, zamiast pozostawić ją
bez próby wysłania komunikatu zamknięcia.

Jeśli PUNCH nie zakończył się sukcesem,
`_close_session()` nie jest wywoływana.

### 16.20. Powiązanie live.py z av_publisher_v14.py

`live.py` odpowiada za odbiór i przygotowanie mediów.

`av_publisher_v14.py` odpowiada za multipleksowanie
oraz ich przekazanie do FFmpeg i MediaMTX.

Współpraca odbywa się przez callbacki:

```python
def on_h264(data):
    submit("video", data)

def on_audio(data):
    submit("audio", data)
```

To przykład oddzielenia odpowiedzialności.

Zmiana sposobu publikacji RTSP nie musi oznaczać
przepisywania całego kodu protokołu kamery.

### 16.21. Co warto zapamiętać?

- `ToSeeBLive` realizuje jedną ograniczoną czasowo sesję.
- Sam moduł nie tworzy encji Home Assistant.
- Potwierdzenia DRW ACK dotyczą pakietów protokołu.
- Dane wideo przechodzą przez bufor kolejności,
  parser i synchronizator H.264.
- Audio jest przekazywane osobnym callbackiem.
- Utrata pakietu może uruchomić odzyskiwanie synchronizacji.
- Statystyki sesji są przechowywane w `LiveStats`.
- Po zakończeniu program próbuje zamknąć sesję PPCS.

**Następny obszar dokumentacji:** `video.py`,
`video_reorder.py` i `audio.py`.


---

## 17. Moduł video.py — składanie i synchronizacja H.264

**Plik:** `src/tosee_b/video.py`

**Rola:** przekształcanie fragmentów danych wideo w kompletne
bloki H.264 oraz kontrolowanie synchronizacji dekodowania.

Moduł nie odbiera sam pakietów UDP i nie publikuje RTSP.
Otrzymuje dane przygotowane przez `live.py`.

### 17.1. Miejsce w architekturze

```text
Pakiety UDP kamery
        |
        v
live.py
        |
        v
VideoReorderBuffer
        |
        | uporządkowane fragmenty
        v
VideoFrameParser
        |
        | obiekty VideoFrame
        v
H264Sync
        |
        | gotowe dane H.264
        v
on_h264()
        |
        v
av_publisher_v14.py
```

### 17.2. Klasa VideoFrame

```python
@dataclass(frozen=True)
class VideoFrame:
    number: int
    h264: bytes
    field2: int
    field3: int
```

Reprezentuje pojedynczy kompletny blok wideo.

- `number` — numer zapisany w nagłówku bloku.
- `h264` — właściwe bajty strumienia H.264.
- `field2` — dodatkowe pole nagłówka ToSee-B.
- `field3` — dodatkowe pole nagłówka ToSee-B.

Znaczenie wszystkich dodatkowych pól protokołu
nie jest tu w pełni określone. Kod wykorzystuje
`field2` i `field3` przy odzyskiwaniu klatki kluczowej.

`frozen=True` ogranicza możliwość zmieniania
atrybutów utworzonego obiektu.

### 17.3. Format bloku ToSee-B

Parser oczekuje nagłówka o długości 16 bajtów.

```text
+----------+----------+----------+----------+
| number   | size     | field2   | field3   |
| 4 bajty  | 4 bajty  | 4 bajty  | 4 bajty  |
+----------+----------+----------+----------+
|           Dane H.264 (size bajtów)        |
+-------------------------------------------+
```

Nagłówek jest odczytywany instrukcją:

```python
number, size, field2, field3 = struct.unpack_from(
    "<IIII", self._buffer
)
```

`<` oznacza kolejność bajtów little-endian.

Każde `I` oznacza 32-bitową liczbę bez znaku.

Pole `size` określa długość danych H.264,
bez 16-bajtowego nagłówka.

### 17.4. Klasa VideoFrameParser

Klasa przechowuje przychodzące dane w buforze:

```python
self._buffer = bytearray()
```

`bytearray` to modyfikowalna tablica bajtów.

Ma to znaczenie, ponieważ jedna porcja danych z UDP
nie musi zawierać całej klatki wideo.

Parser musi umieć zachować niekompletny fragment
i poczekać na dalsze dane.

### 17.5. Ograniczenie wielkości klatki

Domyślny limit wynosi:

```python
max_frame_size = 2 * 1024 * 1024
```

Oznacza to 2 MiB, czyli 2 097 152 bajty.

Niepoprawny limit przy tworzeniu parsera
powoduje `ValueError`.

Podstawowa metoda `feed()` odrzuca deklarowany
rozmiar równy zero lub większy od limitu.

Chroni to przed zaakceptowaniem części uszkodzonych
nagłówków i nierealistycznych rozmiarów klatek.

### 17.6. Właściwość buffered_bytes

```python
@property
def buffered_bytes(self):
    return len(self._buffer)
```

Pozwala sprawdzić, ile bajtów jest aktualnie
przechowywanych w buforze parsera.

`@property` umożliwia odczyt w stylu:

```python
parser.buffered_bytes
```

bez wywoływania metody przez nawiasy.

### 17.7. Metoda reset()

```python
def reset(self):
    self._buffer.clear()
```

Usuwa wszystkie niekompletne dane z bufora.

Jest używana przez `live.py` po wykryciu
zbyt długiej luki w sekwencji pakietów.

Reset nie naprawia utraconych bajtów.
Pozwala natomiast uniknąć dalszego łączenia
nowych danych z potencjalnie uszkodzonym fragmentem.

### 17.8. Metoda feed(data)

To podstawowa metoda przetwarzania obrazu.

Jej przebieg:

1. Dopisuje otrzymane bajty do bufora.
2. Sprawdza, czy dostępny jest 16-bajtowy nagłówek.
3. Odczytuje numer, rozmiar i dodatkowe pola.
4. Sprawdza poprawność rozmiaru.
5. Czeka, jeśli pełne dane klatki jeszcze nie dotarły.
6. Wyodrębnia dane H.264.
7. Sprawdza znacznik początku jednostki Annex B.
8. Tworzy obiekt `VideoFrame`.
9. Usuwa przetworzony blok z bufora.
10. Kontynuuje, jeśli dostępne są następne bloki.

Zwraca listę obiektów `VideoFrame`.

Lista może być pusta, zawierać jedną klatkę
albo kilka klatek, zależnie od dostępnych danych.

### 17.9. Czym jest Annex B?

Annex B to sposób zapisu strumienia H.264,
w którym jednostki NAL są oddzielane kodami startowymi.

W tym projekcie rozpoznawane są:

```text
00 00 01
00 00 00 01
```

Podstawowy parser wymaga, aby dane H.264
rozpoczynały się jednym z tych kodów.

Brak poprawnego kodu początkowego powoduje:

`ValueError("Missing H.264 Annex B start code")`

### 17.10. Funkcja h264_nal_types(data)

Ta funkcja wyszukuje kody startowe Annex B
i odczytuje typ następującej po nich jednostki NAL.

Typ uzyskiwany jest przez:

```python
nal_type = data[header] & 0x1F
```

Wyniki są zwracane w kolejności wystąpienia.

Najważniejsze typy używane przez projekt:

| Typ | Nazwa | Znaczenie |
|---|---|---|
| `7` | SPS | Parametry sekwencji |
| `8` | PPS | Parametry obrazu |
| `6` | SEI | Dodatkowe informacje |
| `5` | IDR | Klatka kluczowa |
| `1` | non-IDR | Dane obrazu zależne od kontekstu |

Funkcja nie wykonuje pełnego dekodowania H.264.
Rozpoznaje typy jednostek na podstawie nagłówków.

### 17.11. Klasa H264Sync

Klasa pilnuje, aby strumień nie rozpoczynał
się od danych, których odbiornik nie potrafi
poprawnie zdekodować bez wcześniejszych parametrów.

Po utworzeniu:

```python
self.synchronized = False
```

Dopóki synchronizacja nie zostanie osiągnięta,
metoda `accept()` wyszukuje właściwą sekwencję
jednostek NAL.

### 17.12. Warunek osiągnięcia synchronizacji

`H264Sync.accept()` wymaga:

1. SPS o typie `7`.
2. PPS o typie `8` występującego później.
3. IDR o typie `5` występującego po PPS.
4. SPS jako pierwszej jednostki NAL w bloku.

Schemat:

```text
SPS (7) --> PPS (8) --> IDR (5)
   |
   +-- musi być pierwszą jednostką NAL
```

Pomiędzy tymi jednostkami mogą występować
inne typy NAL, np. SEI.

Jest to sprawdzenie dostosowane do zaobserwowanego
formatu danych kamery ToSee-B.

Gdy warunek zostanie spełniony,
`self.synchronized` przyjmuje wartość `True`.

Kolejne bloki H.264 są wtedy przekazywane dalej.

### 17.13. Co robi accept(frame)?

Przed synchronizacją:

- analizuje typy NAL;
- odrzuca nieodpowiednie bloki;
- zwraca `None`, jeśli nie osiągnięto synchronizacji.

Po synchronizacji:

- zwraca `frame.h264`.

`None` oznacza tutaj, że dany blok nie powinien
jeszcze zostać przekazany do publikatora.

### 17.14. Dlaczego synchronizacja jest potrzebna?

Strumień wideo zawiera klatki, które mogą zależeć
od wcześniejszych danych.

Jeśli odbiornik rozpocznie odtwarzanie w przypadkowym
miejscu, może nie posiadać informacji niezbędnych
do poprawnego dekodowania obrazu.

SPS, PPS i IDR tworzą odpowiedni punkt rozpoczęcia
dla zaobserwowanego układu ToSee-B.

Synchronizator ogranicza ryzyko przekazywania
niekompletnego początku strumienia.

### 17.15. Metoda feed_keyframe_resync(data)

Jest używana przez aktualny `live.py`
po wykryciu utraty ciągłości pakietów.

Szuka kompletnego bloku spełniającego m.in.
następujące warunki:

- `field2 == 1`;
- `field3 == 0`;
- deklarowany rozmiar od 5 bajtów do limitu;
- początek H.264: `00 00 00 01 67`;
- występowanie PPS typu `8`;
- późniejsze występowanie IDR typu `5`.

Bajt `67` oznacza nagłówek jednostki SPS
w tym zaobserwowanym formacie.

Jeśli blok zostanie znaleziony, metoda
zwraca jeden obiekt `VideoFrame`.

Jeśli nie, zwraca pustą listę.

Przy nadmiernym wzroście bufora metoda zachowuje
co najwyżej ostatnie `max_frame_size + HEADER_SIZE`
bajtów.

### 17.16. Eksperymentalna metoda feed_resync(data)

W kodzie istnieje również metoda:

```python
feed_resync(data)
```

Komentarz źródłowy określa ją jako eksperymentalną.

Nie jest wykorzystywana przez aktualną ścieżkę
transmisji w `live.py`.

Próbuje odnaleźć poprawnie wyglądający blok
na podstawie:

- długości danych;
- kodu startowego Annex B;
- podstawowej poprawności nagłówka NAL.

Takie sprawdzenia nie gwarantują, że odnaleziony
fragment rzeczywiście jest poprawnym początkiem klatki.

Podczas wcześniejszych testów zaobserwowano,
że eksperymentalne wyszukiwanie może zaakceptować
pozornie poprawny kandydat znajdujący się
wewnątrz uszkodzonych danych.

Dlatego należy traktować tę metodę jako narzędzie
rozwojowe, a nie niezawodny mechanizm produkcyjny.

### 17.17. Czym różnią się trzy metody parsera?

| Metoda | Zastosowanie |
|---|---|
| `feed()` | Normalne składanie kolejnych bloków |
| `feed_keyframe_resync()` | Odzyskiwanie po utracie synchronizacji |
| `feed_resync()` | Eksperymentalne wyszukiwanie nagłówka |

W typowym działaniu:

```text
Dane wideo
    |
    v
feed()
    |
    v
H264Sync.accept()
    |
    v
on_h264()
```

Po wykryciu zbyt długiej luki:

```text
Utrata pakietu
    |
    v
Reset parsera i synchronizatora
    |
    v
feed_keyframe_resync()
    |
    v
H264Sync.accept()
    |
    v
on_h264()
```

### 17.18. Czego video.py nie robi?

Moduł nie:

- otwiera połączeń sieciowych;
- wysyła potwierdzeń DRW ACK;
- steruje kamerą;
- uruchamia FFmpeg;
- zapisuje nagrań;
- dekoduje obrazu na piksele;
- odpowiada za kolejność samych datagramów UDP.

Porządkowanie datagramów należy do
`video_reorder.py`, a obsługa sieci do `live.py`.

### 17.19. Podsumowanie dla początkujących

Najważniejsze jest zrozumienie, że:

**Odebrany pakiet UDP nie jest automatycznie gotową
klatką obrazu.**

Dane przechodzą kilka etapów:

1. Odbiór z kamery.
2. Uporządkowanie pakietów.
3. Złożenie kompletnego bloku.
4. Kontrola synchronizacji H.264.
5. Przekazanie do publikatora RTSP.

Każdy etap jest potrzebny z innego powodu.

To dobry przykład architektury, w której
poszczególne klasy mają jasno określone zadania.

**Następny moduł: `video_reorder.py`.**


---

## 18. Moduł video_reorder.py — porządkowanie pakietów UDP

**Plik:** `src/tosee_b/video_reorder.py`

**Główna klasa:** `VideoReorderBuffer`

**Rola:** przechowywanie pakietów wideo przychodzących poza
kolejnością i przekazywanie ich do parsera w prawidłowej
kolejności numerów sekwencyjnych.

### 18.1. Dlaczego potrzebujemy tego modułu?

Protokół UDP nie gwarantuje kolejności dostarczania
pakietów ani tego, że wszystkie pakiety dotrą do odbiorcy.

Przykładowo kamera może wysłać:

```text
100 → 101 → 102 → 103
```

Ale komputer może odebrać:

```text
100 → 102 → 103 → 101
```

Bez bufora dane obrazu mogłyby zostać przekazane do
parsera w niewłaściwej kolejności.

`VideoReorderBuffer` pozwala tymczasowo zatrzymać
pakiety, które wyprzedziły oczekiwany numer.

### 18.2. Gdzie jest wykorzystywany?

W `live.py` tworzony jest obiekt:

```python
self.reorder = VideoReorderBuffer(window_size=128)
```

Dla każdego otrzymanego pakietu kanału wideo
wywoływana jest metoda:

```python
ordered_payloads = self.reorder.push(sequence, payload)
```

Rezultatem jest lista danych, które można już
bezpiecznie przekazać do `VideoFrameParser`.

### 18.3. Konstruktor __init__()

```python
def __init__(self, window_size=16, initial_sequence=None):
```

Parametry:

- `window_size` — maksymalne wyprzedzenie numeru
  sekwencyjnego, jakie bufor może zaakceptować.
- `initial_sequence` — opcjonalny początkowy numer
  oczekiwanego pakietu.

Domyślna wielkość okna wynosi `16`.

W aktualnym `live.py` ustawiono `128`.

Dopuszczalne wartości `window_size` to od 1 do 32767.

### 18.4. Stan bufora

Klasa przechowuje:

```python
self.window_size = window_size
self.expected_sequence = initial_sequence
self._pending = {}
```

`expected_sequence` wskazuje numer pakietu,
którego program aktualnie oczekuje.

`_pending` jest słownikiem przechowującym
pakiety odebrane wcześniej niż brakujący pakiet.

Przykładowy stan:

```text
expected_sequence = 101

_pending:
    102 → dane pakietu 102
    103 → dane pakietu 103
```

Dane 102 i 103 pozostają w buforze,
ponieważ brakuje pakietu 101.

### 18.5. Właściwość has_gap

```python
@property
def has_gap(self):
    return bool(self._pending)
```

Informuje, czy w buforze istnieją pakiety,
których nie można jeszcze przekazać dalej.

Jeśli `_pending` jest pusty, wynik to `False`.

Jeśli zawiera oczekujące pakiety, wynik to `True`.

Ta właściwość jest wykorzystywana przez `live.py`
do kontrolowania czasu trwania luki.

### 18.6. Metoda push(sequence, payload)

To najważniejsza metoda klasy.

Przyjmuje:

- `sequence` — numer pakietu od 0 do 65535;
- `payload` — dane pakietu wideo.

Zwraca listę danych dostępnych w prawidłowej kolejności.

Może zwrócić:

- pustą listę;
- jeden pakiet;
- kilka kolejnych pakietów.

Jeżeli `sequence` znajduje się poza zakresem,
zgłaszany jest `ValueError`.

### 18.7. Pierwszy odebrany pakiet

Jeżeli nie ustalono jeszcze oczekiwanego numeru:

```python
if self.expected_sequence is None:
    self.expected_sequence = sequence
```

Bufor przyjmuje numer pierwszego odebranego
pakietu jako początek śledzenia sekwencji.

Nie oznacza to, że jest to początek klatki H.264.
O synchronizację obrazu dba osobny moduł `video.py`.

### 18.8. Obliczanie odległości sekwencyjnej

Kod używa:

```python
distance = (
    sequence - self.expected_sequence
) % self.SEQUENCE_MODULUS
```

Atrybut:

```python
SEQUENCE_MODULUS = 65536
```

pozwala prawidłowo uwzględniać przejście numerów
sekwencyjnych z `65535` na `0`.

Przykład:

```text
Oczekiwany numer: 65535
Odebrany numer:   0

distance = (0 - 65535) % 65536 = 1
```

Pakiet numer 0 jest więc rozpoznawany jako
następny po 65535, a nie jako bardzo stary.

### 18.9. Odrzucanie starych pakietów

Jeżeli:

```python
distance >= 32768
```

metoda zwraca pustą listę.

Wykorzystuje to zasadę interpretacji 16-bitowej
przestrzeni sekwencyjnej przez jej połowę.

Przy założeniu, że rzeczywiste wyprzedzenie pakietów
nie przekracza połowy przestrzeni numerów, duża
odległość oznacza pakiet znajdujący się za
aktualnie oczekiwanym numerem.

Takie pakiety są traktowane jako stare lub powtórzone.

### 18.10. Ograniczanie wielkości okna

Kod sprawdza:

```python
if distance >= self.window_size:
    return []
```

Pakiety wyprzedzające oczekiwany numer o wartość
równą `window_size` lub większą są ignorowane.

Dzięki temu liczba pakietów przechowywanych
w buforze pozostaje ograniczona.

Większa luka wymaga odrębnego mechanizmu odzyskiwania.

### 18.11. Obsługa duplikatów

```python
if sequence not in self._pending:
    self._pending[sequence] = payload
```

Jeżeli pakiet o danym numerze znajduje się już
w buforze, nowy pakiet o tym samym numerze
nie zastępuje jego danych.

Zapobiega to podwójnemu przechowywaniu pakietów
z tym samym numerem sekwencyjnym.

### 18.12. Wydawanie gotowych pakietów

Kluczową częścią metody `push()` jest pętla:

```python
while self.expected_sequence in self._pending:
    ready.append(
        self._pending.pop(self.expected_sequence)
    )
    self.expected_sequence = (
        self.expected_sequence + 1
    ) % self.SEQUENCE_MODULUS
```

Pętla sprawdza, czy dostępny jest aktualnie
oczekiwany pakiet.

Jeśli tak:

1. Przenosi jego dane do listy `ready`.
2. Usuwa pakiet z bufora.
3. Zwiększa oczekiwany numer.
4. Sprawdza następny numer.

Dzięki temu jednym wywołaniem `push()`
można zwrócić kilka kolejnych pakietów.

### 18.13. Przykład krok po kroku

Załóżmy, że przychodzą pakiety w kolejności:

```text
100, 102, 103, 101
```

| Otrzymany | Zwrócone przez push() | Oczekiwany po operacji |
|---|---|---|
| `100` | `[100]` | `101` |
| `102` | `[]` | `101` |
| `103` | `[]` | `101` |
| `101` | `[101, 102, 103]` | `104` |

W tabeli numery oznaczają pakiety, których dane
zostały zwrócone przez bufor.

Ostatnie wywołanie uwalnia trzy pakiety, ponieważ
brakujący pakiet 101 wreszcie dotarł.

### 18.14. Metoda gap_expired()

```python
def gap_expired(self, now, timeout, gap_started_at):
```

Sprawdza, czy:

- istnieje luka (`has_gap`);
- upłynął wymagany czas oczekiwania.

Wynik jest wartością logiczną `True` albo `False`.

Metoda odrzuca ujemne wartości `timeout`.

Nie uruchamia własnego zegara ani wątku.

Wartości czasu dostarcza kod wywołujący.

### 18.15. Kto kontroluje limit 250 ms?

Limit jest ustawiony w `live.py`:

```python
self._video_gap_timeout = 0.250
```

To właśnie `live.py`:

1. Obserwuje wystąpienie luki.
2. Zapamiętuje moment jej rozpoczęcia.
3. Wywołuje `gap_expired()`.
4. Podejmuje decyzję o odzyskiwaniu transmisji.

Dlatego należy odróżniać odpowiedzialność
bufora od odpowiedzialności klienta LIVE.

### 18.16. Metoda discard_gap()

```python
def discard_gap(self):
    self._pending.clear()
    self.expected_sequence = None
```

Metoda:

- usuwa wszystkie oczekujące pakiety;
- resetuje numer oczekiwanej sekwencji.

Nie usuwa danych znajdujących się już
w `VideoFrameParser` ani nie resetuje H.264.

Te czynności wykonuje osobno `live.py`.

### 18.17. Co dzieje się po zbyt długiej luce?

W aktualnym `live.py` stosowany jest mechanizm:

```text
Brakujący pakiet
       |
       v
Pakiety czekają w _pending
       |
       v
Upływa 250 ms
       |
       v
TOSEE_VIDEO_GAP_TIMEOUT
       |
       v
discard_gap()
       |
       v
Ustawienie nowego expected_sequence
       |
       v
Reset VideoFrameParser
       |
       v
Reset H264Sync
       |
       v
Próba odzyskania klatki kluczowej
```

`live.py` wybiera punkt wznowienia na podstawie
numerów oczekujących pakietów.

Ważne: może to oznaczać odrzucenie części danych
w celu odzyskania stabilnego strumienia.

### 18.18. Czego ten moduł nie robi?

`video_reorder.py` nie:

- odbiera samodzielnie pakietów UDP;
- komunikuje się bezpośrednio z kamerą;
- wysyła potwierdzeń ACK;
- składa kompletnych klatek H.264;
- analizuje SPS, PPS ani IDR;
- uruchamia FFmpeg;
- publikuje RTSP.

Odpowiada wyłącznie za kolejność i przechowywanie
pakietów wideo w ograniczonym oknie sekwencyjnym.

### 18.19. Podsumowanie

`VideoReorderBuffer` jest przykładem dobrze wydzielonej
odpowiedzialności w architekturze programu.

Dzięki niemu logika obsługi kolejności pakietów
nie musi być bezpośrednio mieszana z parsowaniem H.264.

To ułatwia testowanie, analizowanie błędów
i rozwijanie programu.

**Następny moduł do opisania: `audio.py`.**


---

## 19. Moduł audio.py — wyodrębnianie dźwięku G.711 A-law

**Plik:** `src/tosee_b/audio.py`

**Główna funkcja:** `extract_alaw()`

**Rola:** sprawdzanie poprawności ramek audio ToSee-B i usuwanie
nagłówków protokołu, aby otrzymać surowe dane G.711 A-law.

### 19.1. Miejsce modułu w architekturze

```text
Kamera ToSee-B
       |
       | pakiety UDP
       v
live.py
       |
       | DRW kanał 2
       v
audio.extract_alaw()
       |
       | dane G.711 A-law bez nagłówków
       v
on_audio(data)
       |
       v
av_publisher_v14.py
       |
       v
PyAV / kontener NUT
       |
       v
FFmpeg / RTSP / MediaMTX
```

`audio.py` nie otwiera połączenia sieciowego.
Dostaje gotowy ładunek pakietu DRW od `live.py`.

### 19.2. Stałe opisujące ramkę

W module zdefiniowano:

```python
FRAME_SIZE = 332
HEADER_SIZE = 12
AUDIO_SIZE = 320
```

Jedna ramka ma 332 bajty:

- 12 bajtów nagłówka ToSee-B;
- 320 bajtów danych G.711 A-law.

```text
Ramka audio ToSee-B (332 bajty)

+----------------------+-----------------------------+
| Nagłówek ToSee-B     | Dane G.711 A-law             |
| 12 bajtów            | 320 bajtów                  |
+----------------------+-----------------------------+
```

Stała `AUDIO_SIZE` dokumentuje długość części audio.
W aktualnej implementacji funkcja `extract_alaw()`
nie odwołuje się bezpośrednio do tej stałej.

### 19.3. Wzorzec AUDIO_HEADER

Kod definiuje:

```python
AUDIO_HEADER = bytes.fromhex(
    "000000004001000000000000"
)
```

Jest to dokładnie 12 bajtów, których parser oczekuje
na początku każdej ramki audio.

`bytes.fromhex()` przekształca zapis szesnastkowy
w rzeczywiste bajty.

Nie należy interpretować znaczenia poszczególnych pól
tego nagłówka bez dodatkowej analizy protokołu kamery.

Na obecnym etapie wiemy, że kod porównuje nagłówek
z ustalonym wzorcem bajt po bajcie.

### 19.4. Funkcja extract_alaw()

```python
def extract_alaw(payload: bytes) -> bytes:
```

Argument `payload` zawiera jedną lub więcej ramek
audio ToSee-B pobranych z kanału DRW numer 2.

Funkcja zwraca obiekt `bytes`, który zawiera
wyłącznie dane G.711 A-law.

Nie zwraca nagłówków ToSee-B.

### 19.5. Sprawdzanie typu danych

Na początku wykonywany jest warunek:

```python
if not isinstance(payload, bytes):
    raise TypeError("Audio payload must be bytes")
```

Python rozróżnia m.in.:

- `bytes` — niemodyfikowalną sekwencję bajtów;
- `bytearray` — modyfikowalną sekwencję bajtów;
- `str` — tekst.

Ta funkcja wymaga dokładnie danych typu `bytes`
lub jego podklasy, a nie zwykłego tekstu.

### 19.6. Sprawdzanie długości

Następnie kod sprawdza:

```python
if not payload or len(payload) % FRAME_SIZE:
    raise ValueError("Invalid ToSee-B audio payload size")
```

`not payload` oznacza, że przekazane dane są puste.

Operator `%` oblicza resztę z dzielenia.

Poprawny ładunek musi zawierać całkowitą liczbę
ramek o długości 332 bajtów.

Przykłady:

| Długość wejścia | Wynik |
|---|---|
| 0 bajtów | Błąd |
| 332 bajty | 1 ramka |
| 664 bajty | 2 ramki |
| 996 bajtów | 3 ramki |
| 333 bajty | Błąd |

Funkcja nie próbuje zgadywać, gdzie zaczyna się
kolejna ramka w niepoprawnie sformatowanych danych.

### 19.7. Pętla przetwarzająca ramki

Kod wykorzystuje:

```python
for offset in range(0, len(payload), FRAME_SIZE):
    frame = payload[offset:offset + FRAME_SIZE]
```

Dla każdej ramki:

1. Wybiera kolejne 332 bajty.
2. Sprawdza pierwsze 12 bajtów.
3. Odrzuca nagłówek.
4. Dołącza dane audio do wyniku.

Sprawdzanie nagłówka wygląda tak:

```python
if frame[:HEADER_SIZE] != AUDIO_HEADER:
    raise ValueError("Invalid ToSee-B audio frame header")
```

Dane po nagłówku są kopiowane przez:

```python
result.extend(frame[HEADER_SIZE:])
```

Wynik budowany jest w obiekcie `bytearray`,
a na końcu zamieniany na `bytes`.

### 19.8. Przykład z dwiema ramkami

Załóżmy, że `payload` zawiera dwie poprawne
ramki po 332 bajty:

```text
Wejście (664 bajty):

[Nagłówek 12 B][Audio 320 B]
[Nagłówek 12 B][Audio 320 B]

              |
              v
        extract_alaw()
              |
              v

Wyjście (640 bajtów):

[Audio 320 B][Audio 320 B]
```

Kolejność próbek audio zostaje zachowana.

Funkcja usuwa tylko nagłówki protokołu.

### 19.9. Dlaczego 320 bajtów odpowiada 40 ms?

Wersja v14 konfiguruje audio jako:

- G.711 A-law;
- 8000 próbek na sekundę;
- jeden kanał (mono).

G.711 A-law zapisuje jedną próbkę w jednym bajcie.

Dlatego 320 bajtów oznacza 320 próbek.

```text
320 próbek / 8000 próbek/s = 0,04 s = 40 ms
```

Dwie ramki reprezentują więc 80 ms dźwięku.

To obliczenie wynika z parametrów G.711 A-law
używanych przez aktualny publikator.

### 19.10. Czy moduł dekoduje dźwięk?

Nie.

`extract_alaw()` nie zamienia G.711 A-law
na nieskompresowany PCM.

Nie zmienia również częstotliwości próbkowania.

Zwraca zakodowane bajty audio po usunięciu
nagłówków protokołu ToSee-B.

W `av_publisher_v14.py` dane są przekazywane
do strumienia PyAV typu `pcm_alaw`.

FFmpeg jest uruchamiany z opcją `-c:a copy`.

### 19.11. Współpraca z live.py

W metodzie `_receive()` klasy `ToSeeBLive`
obsługa kanału numer 2 zawiera:

```python
elif channel == 2:
    self.stats.audio_packets += 1
    if self.on_audio is not None:
        self.on_audio(extract_alaw(payload))
```

Oznacza to, że:

1. Zwiększany jest licznik pakietów audio.
2. Sprawdzana jest obecność callbacku.
3. Wyodrębniane są dane G.711 A-law.
4. Callback przekazuje je do dalszego przetwarzania.

Jeżeli `on_audio` wynosi `None`, w tej gałęzi kodu
nie jest wywoływane `extract_alaw()`.

### 19.12. Współpraca z SafeToSeeBLive

Wersja v14 używa klasy `SafeToSeeBLive`,
dziedziczącej po `ToSeeBLive`.

Przechwytuje ona dwa konkretne komunikaty
błędów `ValueError` pochodzące z `audio.py`:

```text
Invalid ToSee-B audio payload size
Invalid ToSee-B audio frame header
```

W takim przypadku zapisuje:

`AUDIO_INVALID_PACKET_SKIPPED`

i pozwala kontynuować sesję.

Nie oznacza to ignorowania wszystkich błędów.
Inne rodzaje wyjątków nadal mogą przerwać transmisję.

### 19.13. Zestawienie błędów

| Sytuacja | Wyjątek |
|---|---|
| Dane nie są typu `bytes` | `TypeError` |
| Pusty ładunek | `ValueError` |
| Długość niepodzielna przez 332 | `ValueError` |
| Nieprawidłowy nagłówek ramki | `ValueError` |

Jeżeli choć jedna ramka ma niepoprawny nagłówek,
funkcja zgłasza wyjątek i nie zwraca częściowego wyniku.

### 19.14. Związek z synchronizacją v14

`audio.py` nie ustala znaczników czasu PTS ani DTS.

Wersja v14 wyznacza te znaczniki później,
w multiplekserze PyAV.

To właśnie tam ustawiono korektę:

```python
audio_offset_ms = -300
```

Dlatego trzeba rozróżniać dwa etapy:

- `audio.py` — wydobywa właściwe bajty audio;
- `av_publisher_v14.py` — umieszcza audio w strumieniu
  multimedialnym i nadaje mu znaczniki czasowe.

### 19.15. Co warto zapamiętać?

`audio.py` to przykład małego modułu o jednej
dobrze określonej odpowiedzialności.

Nie musi wiedzieć, gdzie znajduje się kamera,
jaki jest adres MQTT ani gdzie działa MediaMTX.

Otrzymuje bajty, sprawdza ich format i zwraca
gotowe dane audio G.711 A-law.

Dzięki temu można testować poprawność ramek
bez uruchamiania prawdziwej kamery.

**Następny obszar dokumentacji: protokół DRW,
potwierdzenia ACK i komendy sterujące.**


---

## 20. Moduł drw.py — odczytywanie pakietów DRW

**Plik:** `src/tosee_b/drw.py`

**Funkcja:** `parse_drw_packet(packet)`

### 20.1. Do czego służy?

Moduł rozpoznaje przychodzące komunikaty PPCS DRW.

Jego zadaniem jest wydobycie trzech informacji:

- numeru kanału;
- numeru sekwencyjnego;
- właściwych danych pakietu.

Sam nie odbiera datagramów UDP. Otrzymuje je od
modułu `live.py`.

### 20.2. Funkcja parse_drw_packet()

```python
def parse_drw_packet(packet: bytes):
```

Funkcja najpierw sprawdza typ argumentu:

```python
if not isinstance(packet, bytes):
    return None
```

Następnie wywołuje:

```python
plain = decrypt_packet(packet)
```

Oznacza to, że przed interpretacją pól protokołu
pakiet przechodzi przez warstwę kryptograficzną.

### 20.3. Sprawdzanie poprawności

Parser wymaga:

1. Poprawnego pakietu PPCS według `is_valid_ppcs_packet()`.
2. Długości odszyfrowanych danych wynoszącej co najmniej 8 bajtów.
3. Wartości `0xD0` na pozycji 1.
4. Wartości `0xD1` na pozycji 4.

Jeżeli warunki nie są spełnione, zwraca `None`.

Szczegóły walidacji wykonywanej przez
`is_valid_ppcs_packet()` opiszemy w rozdziale `crypto.py`.

### 20.4. Struktura odczytywanego pakietu

```text
Po odszyfrowaniu:

Bajt 0        : 0xF1 (zgodnie z formatem budowanych pakietów)
Bajt 1        : 0xD0
Bajty 2–3     : długość według formatu PPCS
Bajt 4        : 0xD1
Bajt 5        : kanał
Bajty 6–7     : numer sekwencyjny, big-endian
Bajty 8–koniec: dane
```

Znaczenie bajtu 0 oraz pola długości wymaga
pełnego powiązania z implementacją `crypto.py`.

Parser odczytuje:

```python
channel = plain[5]
sequence = int.from_bytes(plain[6:8], "big")
data = plain[8:]
```

### 20.5. Co oznacza big-endian?

Big-endian oznacza, że starszy bajt liczby
jest zapisywany przed młodszym.

Przykładowo:

```text
Bajty: 01 02
Liczba: 258
```

W Pythonie:

```python
int.from_bytes(b"\x01\x02", "big")  # 258
```

Tak właśnie interpretowane są numery sekwencyjne DRW.

### 20.6. Co zwraca funkcja?

Dla rozpoznanego pakietu:

```python
(channel, sequence, data)
```

Jest to krotka (*tuple*) trzech elementów.

Dla pakietu nierozpoznanego:

```python
None
```

Funkcja nie przekształca danych H.264 ani audio.
Zwraca surowe dane kanału DRW do dalszej obsługi.

### 20.7. Współpraca z live.py

W `ToSeeBLive._receive()` znajduje się:

```python
drw = parse_drw_packet(packet)

if drw is not None:
    channel, sequence, payload = drw
```

Następnie `live.py` obsługuje kanały:

| Kanał | Rola w live.py |
|---|---|
| `0` | Sterowanie |
| `1` | Wideo |
| `2` | Audio |

Rozdzielenie parsowania pakietów i ich obsługi
ułatwia testowanie kodu.

---

## 21. Moduł ack.py — potwierdzenia odbioru DRW

**Plik:** `src/tosee_b/ack.py`

**Funkcja:** `build_drw_ack(channel, sequences)`

### 21.1. Co to jest ACK?

ACK oznacza *acknowledgement*, czyli potwierdzenie odbioru.

W protokole ToSee-B służy do informowania urządzenia,
które numery sekwencyjne zostały odebrane.

ACK nie jest automatycznie potwierdzeniem,
że obraz został poprawnie wyświetlony.

### 21.2. Argumenty funkcji

```python
def build_drw_ack(channel: int, sequences: list[int]) -> bytes:
```

- `channel` — numer kanału od 0 do 255;
- `sequences` — lista numerów sekwencyjnych do potwierdzenia.

Każdy numer sekwencyjny musi należeć do zakresu
od 0 do 65535.

Lista nie może być pusta ani zawierać więcej
niż 32765 elementów.

### 21.3. Weryfikacja danych

Funkcja zgłasza `ValueError`, gdy:

- numer kanału ma niepoprawny typ lub wartość;
- lista potwierdzeń jest pusta lub za długa;
- któryś numer sekwencyjny ma niepoprawny typ lub wartość.

Nie usuwa powtórzonych numerów z listy.

Oznacza to, że argument zawierający duplikaty
zostanie zachowany w konstrukcji komunikatu.

### 21.4. Tworzenie danych potwierdzenia

```python
payload = struct.pack(
    ">BBH", 0xD1, channel, len(sequences)
)
```

Format `>BBH` oznacza:

- `>` — big-endian;
- `B` — liczba 8-bitowa;
- `B` — kolejna liczba 8-bitowa;
- `H` — liczba 16-bitowa.

Pierwsze cztery bajty danych zawierają:

```text
0xD1 | kanał | liczba potwierdzeń (2 bajty)
```

Po nich dopisywane są numery sekwencyjne,
każdy zapisany w dwóch bajtach:

```python
struct.pack(">H", seq)
```

### 21.5. Nagłówek i szyfrowanie

Następnie tworzony jest nagłówek PPCS:

```python
header = struct.pack(
    ">BBH", 0xF1, 0xD1, len(payload)
)
```

Gotowy komunikat powstaje przez:

```python
return encrypt_packet(header + payload)
```

Wynik jest zaszyfrowanym pakietem gotowym
do przekazania do funkcji wysyłającej UDP.

### 21.6. Przykład użycia w live.py

```python
self.sock.sendto(
    build_drw_ack(channel, [sequence]),
    self.address,
)
```

W tym przypadku program potwierdza pojedynczy
numer sekwencyjny otrzymanego pakietu.

ACK jest wysyłany dla kanałów 0, 1 i 2.

### 21.7. Czego ack.py nie robi?

Moduł nie:

- odbiera danych z sieci;
- oczekuje na odpowiedź kamery;
- prowadzi listy odebranych pakietów;
- decyduje o ponawianiu transmisji;
- analizuje zawartości obrazu lub dźwięku.

Jego zadaniem jest wyłącznie przygotowanie
poprawnego komunikatu potwierdzenia.

---

## 22. Moduł commands.py — budowanie poleceń kamery

**Plik:** `src/tosee_b/commands.py`

**Funkcje:**

- `build_control_command()`;
- `build_drw_packet()`;
- `build_init_command()`.

### 22.1. Do czego służy?

Moduł buduje komunikaty sterujące protokołu ToSee-B.

W odróżnieniu od `drw.py`, który odczytuje
przychodzące pakiety, ten moduł tworzy komunikaty
przeznaczone do wysłania do kamery.

### 22.2. build_control_command(command)

```python
def build_control_command(command: int) -> bytes:
```

Funkcja wymaga wartości `command`
z zakresu 0 do `0xFFFFFFFF`.

Następnie wykonuje:

```python
return struct.pack("<II", command, 0)
```

Wynikiem jest osiem bajtów.

Format `<II` oznacza dwie 32-bitowe liczby
bez znaku w kolejności little-endian.

Pierwsza zawiera kod polecenia,
druga zawiera zero.

### 22.3. Czym jest little-endian?

W little-endian najmłodszy bajt liczby
jest zapisywany jako pierwszy.

Przykładowo:

```text
Liczba: 0x01020304

Big-endian:    01 02 03 04
Little-endian: 04 03 02 01
```

Prawidłowy porządek bajtów jest niezbędny,
aby kamera poprawnie zinterpretowała komunikat.

### 22.4. build_drw_packet(sequence, command)

```python
def build_drw_packet(sequence: int, command: int) -> bytes:
```

Funkcja tworzy zaszyfrowany pakiet sterujący
DRW na kanale numer 0.

Najpierw sprawdza numer sekwencyjny:

```python
if not 0 <= sequence <= 0xFFFF:
    raise ValueError(
        "Sequence must be a 16-bit unsigned integer"
    )
```

Następnie buduje dane kanału:

```python
channel_data = struct.pack(
    ">BBH", 0xD1, 0, sequence
)
```

Dokłada ośmiobajtowe polecenie:

```python
payload = channel_data + build_control_command(command)
```

Tworzy nagłówek PPCS:

```python
header = struct.pack(
    ">BBH", 0xF1, 0xD0, len(payload)
)
```

Na końcu szyfruje pakiet:

```python
return encrypt_packet(header + payload)
```

### 22.5. Struktura komunikatu sterującego

```text
PPCS:
  0xF1
  0xD0
  długość payload (2 bajty, big-endian)

DRW:
  0xD1
  kanał 0
  numer sekwencyjny (2 bajty, big-endian)

Polecenie:
  kod polecenia (4 bajty, little-endian)
  zero (4 bajty, little-endian)
```

Wynik jest następnie szyfrowany przez `crypto.py`.

### 22.6. build_init_command(client_uuid)

Ta funkcja tworzy 184-bajtowy ładunek inicjalizacji.

Parametrem jest identyfikator UUID klienta,
zapisany w kanonicznej postaci tekstowej.

Przykład formatu:

```text
12345678-1234-4234-8234-123456789abc
```

Jest to przykładowy UUID, a nie sekret kamery.

Program sprawdza format przez:

```python
parsed = uuid.UUID(client_uuid)
```

Dodatkowo porównuje reprezentację kanoniczną
z wartością przekazaną przez wywołującego.

### 22.7. Budowa ładunku inicjalizacji

Kod tworzy bufor:

```python
payload = bytearray(184)
```

Następnie wpisuje:

```python
struct.pack_into("<II", payload, 0, 0, 176)
```

Pozostałe jawnie ustawiane fragmenty to:

| Pozycja w bajtach | Dane |
|---|---|
| `0x0C:0x0E` | `11` |
| `0x12:0x17` | `1.0.0` |
| `0x32:0x56` | UUID klienta (36 znaków ASCII) |

Pozostałe bajty zachowują początkową wartość zero.

Nie przypisujemy tutaj niepotwierdzonych znaczeń
poszczególnym polom protokołu.

Komentarz w kodzie wskazuje, że dokładna rola
identyfikatora UUID nie jest jeszcze potwierdzona.

### 22.8. Jak moduł współpracuje z live.py?

W metodzie `ToSeeBLive.run()` tworzona jest
sekwencja czterech komunikatów:

```python
commands = (
    (0, build_init_drw_packet(self.client_uuid)),
    (1, build_drw_packet(1, 1)),
    (2, build_drw_packet(2, 5)),
    (3, build_drw_packet(3, 3)),
)
```

Istotne rozróżnienie:

- `build_drw_packet()` pochodzi z `commands.py`;
- `build_init_drw_packet()` pochodzi z `session.py`;
- `build_init_command()` z `commands.py` przygotowuje
  ładunek inicjalizacji, ale sam nie stanowi całej
  zaszyfrowanej wiadomości PPCS.

Szczegółowy sposób budowania pakietu inicjalizacji
zobaczymy przy analizie `session.py`.

### 22.9. Porównanie trzech modułów

| Moduł | Kierunek | Operacja |
|---|---|---|
| `drw.py` | Kamera → Python | Odszyfrowanie i odczyt DRW |
| `ack.py` | Python → kamera | Utworzenie potwierdzenia |
| `commands.py` | Python → kamera | Utworzenie polecenia |

Wszystkie współpracują z `live.py`,
ale żaden z nich samodzielnie nie prowadzi
pełnej sesji sieciowej.

### 22.10. Co warto zapamiętać?

Na najniższym poziomie nasz program
nie przesyła obiektów Pythona ani tekstowych poleceń.

Przesyła uporządkowane ciągi bajtów.

Dlatego istotne są:

- długości poszczególnych pól;
- kolejność bajtów;
- numery sekwencyjne;
- numery kanałów;
- poprawne szyfrowanie;
- potwierdzenia odbioru.

**Następne moduły do opisania: `session.py`,
`crypto.py`, `punch.py` i `transport.py`.**


---

## 23. Moduł session.py — inicjalizacja sesji i potwierdzenia DRW

**Plik:** `src/tosee_b/session.py`

**Rola:** przygotowanie pakietu inicjalizacji kamery, odczytywanie
potwierdzeń DRW_ACK oraz śledzenie dwóch rodzajów odpowiedzi.

### 23.1. Miejsce w architekturze

```text
                  live.py
                     |
                     +-- build_init_drw_packet()
                     |         |
                     |         +-- commands.build_init_command()
                     |         +-- crypto.encrypt_packet()
                     |
                     +-- parse_drw_ack()
                               |
                               +-- crypto.decrypt_packet()
                               +-- crypto.is_valid_ppcs_packet()
```

Moduł `session.py` nie otwiera sam połączenia UDP.

Przygotowuje lub interpretuje wiadomości,
a ich wysyłaniem i odbieraniem zajmuje się `live.py`.

### 23.2. Funkcja build_init_drw_packet()

```python
def build_init_drw_packet(client_uuid: str) -> bytes:
```

Funkcja tworzy pierwszy komunikat inicjalizacji,
przeznaczony dla kanału sterującego numer 0.

Numer sekwencyjny tego komunikatu wynosi 0.

Najpierw wywołuje:

```python
data = build_init_command(client_uuid)
```

Funkcja z `commands.py` przygotowuje 184-bajtowy
ładunek inicjalizacji zawierający między innymi UUID klienta.

Następnie dodawany jest nagłówek kanału DRW:

```python
payload = struct.pack(">BBH", 0xD1, 0, 0) + data
```

Oznacza to:

- `0xD1` — znacznik danych kanału;
- `0` — kanał sterujący;
- `0` — numer sekwencyjny zapisany na dwóch bajtach;
- `data` — właściwy ładunek inicjalizacji.

### 23.3. Budowa pakietu PPCS

Dalej wykonywana jest operacja:

```python
return encrypt_packet(
    struct.pack(">BBH", 0xF1, 0xD0, len(payload))
    + payload
)
```

Format `>BBH` oznacza:

- `>` — big-endian;
- `B` — liczba 8-bitowa;
- `B` — kolejna liczba 8-bitowa;
- `H` — liczba 16-bitowa.

Ponieważ ładunek inicjalizacji ma 184 bajty,
a nagłówek DRW 4 bajty, całe `payload` ma 188 bajtów.

Zewnętrzny nagłówek PPCS ma 4 bajty.

Przed zaszyfrowaniem komunikat ma zatem 192 bajty.

Długość ostatecznego wyniku szyfrowania zależy od
implementacji `encrypt_packet()` w `crypto.py`.

### 23.4. Funkcja parse_drw_ack()

```python
def parse_drw_ack(packet: bytes):
```

Funkcja analizuje otrzymane zaszyfrowane
potwierdzenie DRW_ACK.

Jeśli argument nie jest typu `bytes`,
zwraca `None`.

Następnie odszyfrowuje pakiet:

```python
plain = decrypt_packet(packet)
```

### 23.5. Warunki poprawności DRW_ACK

Parser sprawdza:

1. Poprawność PPCS przez `is_valid_ppcs_packet()`.
2. Minimalną długość 8 bajtów.
3. Wartość `0xD1` na pozycji 1.
4. Wartość `0xD1` na pozycji 4.

Jeżeli któryś warunek nie jest spełniony,
funkcja zwraca `None`.

Dzięki temu zwykłe pakiety DRW nie są
interpretowane jako potwierdzenia DRW_ACK.

### 23.6. Budowa potwierdzenia

Odszyfrowany komunikat DRW_ACK ma postać:

```text
+------------+-------------+-------------+-------------------+
| PPCS       | DRW_ACK     | Liczba ACK  | Numery sekwencji |
| 4 bajty    | 2 bajty     | 2 bajty     | po 2 bajty       |
+------------+-------------+-------------+-------------------+
```

Parser odczytuje:

```python
channel = plain[5]
count = int.from_bytes(plain[6:8], "big")
```

`count` oznacza liczbę potwierdzanych sekwencji.

Następnie sprawdzana jest długość:

```python
if len(plain) != 8 + 2 * count:
    return None
```

Potwierdzenie zawiera 8 bajtów części stałej
i po 2 bajty na każdy numer sekwencyjny.

### 23.7. Odczytywanie numerów sekwencyjnych

Numery odczytywane są w pętli:

```python
sequences = [
    int.from_bytes(plain[8 + i*2:10 + i*2], "big")
    for i in range(count)
]
```

Jest to przykład *list comprehension*,
czyli tworzenia listy za pomocą wyrażenia.

Każdy numer odczytywany jest jako
16-bitowa liczba big-endian.

Wynik funkcji:

```python
(channel, sequences)
```

Przykładowo może wyglądać tak:

```python
(0, [0, 1, 2])
```

Jeżeli pakiet nie zostanie rozpoznany,
wynikiem jest `None`.

### 23.8. Klasa InitResponseTracker

```python
class InitResponseTracker:
```

Klasa śledzi dwa niezależne warunki:

```python
self.ack_received = False
self.response_received = False
```

Pierwszy oznacza otrzymanie potwierdzenia ACK.

Drugi oznacza rozpoznanie odpowiedzi DRW.

Klasa dotyczy inicjalizacji o numerze sekwencyjnym 0.

### 23.9. Metoda accept(packet)

Metoda próbuje rozpoznać przekazany pakiet.

Najpierw sprawdza, czy jest to DRW_ACK
dla kanału 0 zawierający sekwencję 0.

Jeśli tak:

```python
self.ack_received = True
```

i zwraca `True`.

Jeśli nie rozpoznano potwierdzenia ACK,
próbuje zinterpretować pakiet jako zwykły DRW.

Dla kanału 0 i sekwencji 0 ustawia:

```python
self.response_received = True
```

i również zwraca `True`.

Inne wiadomości nie zmieniają tych flag
i metoda zwraca `False`.

### 23.10. Właściwość complete

```python
@property
def complete(self):
    return self.ack_received and self.response_received
```

Oznacza to, że oba warunki muszą być spełnione.

| ACK | Odpowiedź DRW | complete |
|---|---|---|
| Nie | Nie | `False` |
| Tak | Nie | `False` |
| Nie | Tak | `False` |
| Tak | Tak | `True` |

Kolejność otrzymania wiadomości nie ma znaczenia.

### 23.11. Dlaczego kolejność może być różna?

Komunikaty są przesyłane przez UDP.

Kod nie może zakładać, że potwierdzenie ACK
i odpowiedź DRW zawsze przyjdą w tej samej kolejności.

Dlatego `InitResponseTracker` przechowuje dwa stany
niezależnie od siebie.

To przykład prostego automatu stanu w Pythonie.

### 23.12. Ważna różnica względem live.py

Aktualny `live.py` bezpośrednio importuje:

```python
from .session import build_init_drw_packet, parse_drw_ack
```

Natomiast nie wykorzystuje klasy `InitResponseTracker`.

Zamiast niej metoda `_exchange()` samodzielnie
śledzi ACK i odpowiedź dla każdej sekwencji,
a następnie dodatkowo sprawdza treść odpowiedzi
przez `_valid_response()`.

To istotne rozróżnienie:

**`InitResponseTracker.complete` sprawdza obecność obu
rodzajów komunikatów, ale nie weryfikuje zawartości
odpowiedzi sterującej.**

### 23.13. Co warto zapamiętać?

- `session.py` przygotowuje komunikat inicjalizacji.
- Numer sekwencyjny inicjalizacji wynosi 0.
- Pakiet powstaje z ładunku z `commands.py`.
- Szyfrowanie wykonuje `crypto.py`.
- DRW_ACK może zawierać kilka numerów sekwencyjnych.
- ACK i odpowiedź DRW to osobne komunikaty.
- `InitResponseTracker` rozpoznaje je niezależnie.
- Aktualny `live.py` ma własną logikę wymiany sterującej.

**Następny moduł do opisania: `crypto.py`.**


---

## 24. Moduł crypto.py — szyfrowanie pakietów PPCS

**Plik:** `src/tosee_b/crypto.py`

**Rola:** szyfrowanie i odszyfrowywanie komunikatów PPCS
oraz podstawowa walidacja ich nagłówków.

### 24.1. Dlaczego potrzebny jest ten moduł?

Kamera ToSee-B nie przesyła wszystkich komunikatów PPCS
w postaci bezpośrednio czytelnych struktur bajtowych.

Dlatego zanim `drw.py` lub `session.py` odczytają
zawartość wiadomości, wykonują jej odszyfrowanie.

Podobnie przed wysłaniem komendy lub potwierdzenia ACK
program przygotowuje i szyfruje odpowiedni pakiet.

Schemat:

```text
WYSYŁANIE:

commands.py / ack.py / session.py
          |
          v
    Jawne bajty PPCS
          |
          v
    encrypt_packet()
          |
          v
      Pakiet UDP
          |
          v
      Kamera ToSee-B


ODBIERANIE:

      Kamera ToSee-B
          |
          v
      Pakiet UDP
          |
          v
    decrypt_packet()
          |
          v
    Jawne bajty PPCS
          |
          v
    drw.py / session.py
```

### 24.2. Tablica XOR_TABLE

Moduł zawiera stałą `XOR_TABLE`, zdefiniowaną
za pomocą `bytes.fromhex()`.

Tablica zawiera wartości bajtowe wykorzystywane
do wyznaczania przekształcenia XOR.

Każdy jej element ma wartość z zakresu 0–255.

Kod wskazuje, że tablica pochodzi z projektu
`cloudedge-client` udostępnianego na licencji GPLv3.

Jest to ważna informacja o pochodzeniu kodu
i danych algorytmu.

Przy dalszym rozpowszechnianiu projektu należy
zachować właściwe informacje licencyjne i atrybucję.

### 24.3. Czterobajtowy stan szyfru

W module istnieje stała:

```python
DEFAULT_STATE = bytes.fromhex("fd034d4f")
```

Stan zawiera dokładnie cztery bajty.

Komentarz w kodzie informuje, że stan odtworzono
na podstawie dwóch niezależnych przechwyceń
komunikacji ToSee-B.

Nie potwierdzono jego uniwersalności dla innych
urządzeń ani innych wersji firmware.

Zarówno `encrypt_packet()`, jak i `decrypt_packet()`
pozwalają przekazać własny stan przez argument `state`.

### 24.4. Dlaczego stan musi mieć cztery bajty?

Obie funkcje zawierają sprawdzenie:

```python
if len(state) != 4:
    raise ValueError(
        "PPCS cipher state must contain exactly 4 bytes"
    )
```

W dalszej części algorytmu występuje:

```python
state[previous & 3]
```

Operacja `previous & 3` daje indeks od 0 do 3,
czyli wybiera jeden z czterech bajtów stanu.

### 24.5. Co to jest XOR?

XOR to operacja logiczna wykonywana na bitach.

Dla jednego bitu:

| A | B | A XOR B |
|---|---|---|
| 0 | 0 | 0 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 0 |

W Pythonie XOR zapisujemy operatorem `^`.

Przykład:

```python
12 ^ 5  # wynik: 9
```

Przy ponownym użyciu tej samej wartości XOR
można odtworzyć pierwotne dane:

```python
(12 ^ 5) ^ 5  # wynik: 12
```

W tym projekcie wartość używana przez XOR
zmienia się zależnie od poprzedniego bajtu
zaszyfrowanego pakietu i stanu szyfru.

### 24.6. Funkcja encrypt_packet()

Sygnatura:

```python
def encrypt_packet(data: bytes, state: bytes = DEFAULT_STATE) -> bytes:
```

Funkcja:

1. Sprawdza długość stanu.
2. Tworzy pusty bufor wyniku.
3. Ustawia `previous = 0`.
4. Przechodzi kolejno przez bajty danych wejściowych.
5. Oblicza indeks tablicy XOR.
6. Szyfruje bieżący bajt.
7. Dopisuje go do wyniku.
8. Zapamiętuje zaszyfrowany bajt jako `previous`.

Najważniejszy fragment:

```python
index = (previous + state[previous & 3]) & 0xff
encrypted = value ^ XOR_TABLE[index]
result.append(encrypted)
previous = encrypted
```

Operator `& 0xff` ogranicza wynik do zakresu
jednego bajtu, czyli 0–255.

### 24.7. Funkcja decrypt_packet()

Sygnatura:

```python
def decrypt_packet(data: bytes, state: bytes = DEFAULT_STATE) -> bytes:
```

Funkcja wykorzystuje tę samą tablicę i ten sam
sposób obliczania indeksu.

Kluczowy fragment:

```python
index = (previous + state[previous & 3]) & 0xff
result.append(value ^ XOR_TABLE[index])
previous = value
```

Różnica znajduje się w ostatniej instrukcji.

Przy odszyfrowywaniu `value` jest bajtem
zaszyfrowanym otrzymanym na wejściu.

Przy szyfrowaniu zapamiętywany jest bajt
dopiero co zaszyfrowany.

W obu przypadkach następny krok zależy więc
od poprzedniego bajtu zaszyfrowanej wiadomości.

### 24.8. Porównanie szyfrowania i odszyfrowywania

| Operacja | Zawartość `previous` po kroku |
|---|---|
| `encrypt_packet()` | Wytworzony bajt zaszyfrowany |
| `decrypt_packet()` | Odebrany bajt zaszyfrowany |

Dzięki temu obie funkcje mogą obliczać
zgodne indeksy `XOR_TABLE`.

Nie wolno bez przemyślenia zamieniać tych instrukcji,
ponieważ zmieniłoby to wynik kolejnych iteracji.

### 24.9. Czy jest to AES albo TLS?

Nie.

Widzimy własny, zależny od stanu mechanizm XOR,
używany dla zgodności z protokołem PPCS.

Nie należy traktować go jako odpowiednika
nowoczesnego, uwierzytelnionego szyfrowania.

Moduł nie zawiera mechanizmu weryfikacji
autentyczności wiadomości porównywalnego z AEAD.

Sprawdzanie poprawności nagłówka PPCS to nie to samo
co kryptograficzna ochrona integralności.

### 24.10. Funkcja is_valid_ppcs_packet()

Sygnatura:

```python
def is_valid_ppcs_packet(data: bytes) -> bool:
```

Funkcja sprawdza:

1. Czy komunikat ma przynajmniej cztery bajty.
2. Czy pierwszy bajt ma wartość `0xF1`.
3. Czy pole długości zgadza się z liczbą bajtów
   znajdujących się za czterobajtowym nagłówkiem.

Kod:

```python
return (
    len(data) >= 4
    and data[0] == 0xf1
    and int.from_bytes(data[2:4], "big") == len(data) - 4
)
```

Funkcja interpretuje długość jako liczbę
16-bitową w kolejności big-endian.

Nie sprawdza samodzielnie konkretnego typu
wiadomości zapisanego w drugim bajcie.

To robią moduły wyższego poziomu,
np. `drw.py` oraz `session.py`.

### 24.11. Co oznacza pole długości?

Załóżmy, że odszyfrowany pakiet zawiera:

```text
Nagłówek PPCS: 4 bajty
Dane:          12 bajtów
Cały pakiet:   16 bajtów
```

Wtedy pole długości powinno zawierać `12`.

Funkcja porównuje tę wartość z:

```python
len(data) - 4
```

Jeżeli wartości się różnią, pakiet
nie przechodzi podstawowej walidacji.

### 24.12. Współpraca z pozostałymi modułami

| Moduł | Korzystanie z crypto.py |
|---|---|
| `drw.py` | Odszyfrowywanie i walidacja przychodzących DRW |
| `ack.py` | Szyfrowanie potwierdzeń DRW_ACK |
| `commands.py` | Szyfrowanie komend sterujących |
| `session.py` | Szyfrowanie inicjalizacji i odczyt DRW_ACK |
| `live.py` | Szyfrowanie i odszyfrowywanie zamknięcia PPCS |

Dzięki centralizacji algorytmu inne moduły
nie muszą implementować własnych kopii szyfru.

### 24.13. Ważne ograniczenia i bezpieczeństwo

- Stan szyfru potwierdzono tylko dla badanego urządzenia.
- Zgodność z innymi wersjami firmware jest nieustalona.
- Podstawowa walidacja nagłówka nie gwarantuje,
  że wiadomość pochodzi z zaufanego urządzenia.
- Nie należy interpretować własnego algorytmu XOR
  jako silnej ochrony poufności transmisji.
- Dane i kod pochodzące z innych projektów wymagają
  zachowania właściwych informacji licencyjnych.

### 24.14. Podsumowanie dla początkujących

`crypto.py` jest przykładem modułu niskiego poziomu.

Otrzymuje bajty i zwraca bajty.

Nie wie, czy wewnątrz wiadomości znajduje się
obraz, dźwięk, potwierdzenie czy polecenie kamery.

Za interpretowanie treści odpowiadają inne moduły.

To pozwala oddzielić trzy operacje:

1. Odbiór pakietu UDP.
2. Odszyfrowanie pakietu PPCS.
3. Interpretowanie danych konkretnego protokołu.

**Następne moduły: `punch.py` i `transport.py`.**


---

## 25. Moduł punch.py — pakiety PUNCH i PUNCH_ACK

**Plik:** `src/tosee_b/punch.py`

**Rola:** przygotowywanie pakietu rozpoczynającego komunikację
PPCS oraz sprawdzanie odpowiedzi urządzenia.

Moduł nie otwiera gniazda UDP. Buduje i sprawdza bajty
przekazywane następnie przez `transport.py`.

### 25.1. Dlaczego potrzebny jest PUNCH?

Zanim `live.py` rozpocznie właściwą wymianę poleceń
sterujących DRW, wywołuje:

```python
perform_punch(self.sock, self.address, self.did)
```

Funkcja ta korzysta z `punch.py`, aby przygotować
komunikat PUNCH i sprawdzić odpowiedź PUNCH_ACK.

Jest to etap uzgodnienia komunikacji PPCS.

Nie należy zakładać, że samo wysłanie PUNCH budzi
każdą kamerę ToSee-B ze stanu uśpienia.

### 25.2. Identyfikator DID

DID jest identyfikatorem urządzenia używanym
w komunikacji z kamerą.

W analizowanej implementacji musi mieć dokładnie
20 bajtów i być typu `bytes`.

Nie jest to zwykły tekst o dowolnej długości.

Kod sprawdzający argument:

```python
if not isinstance(did, bytes) or len(did) != 20:
    raise ValueError("DID must be exactly 20 bytes")
```

Wartość DID nie powinna być publikowana w przykładach
z rzeczywistej konfiguracji urządzenia.

### 25.3. Funkcja build_punch_packet()

Sygnatura:

```python
def build_punch_packet(did: bytes) -> bytes:
```

Funkcja tworzy następującą strukturę przed szyfrowaniem:

```python
plain = struct.pack(">BBH", 0xF1, 0x41, 20) + did
```

Poszczególne pola oznaczają:

| Pole | Długość | Wartość |
|---|---|---|
| Znacznik PPCS | 1 bajt | `0xF1` |
| Typ wiadomości | 1 bajt | `0x41` |
| Długość danych | 2 bajty | `20` |
| DID | 20 bajtów | Identyfikator urządzenia |

Cały komunikat przed zaszyfrowaniem ma 24 bajty.

`>BBH` wskazuje zapis big-endian dla pola długości.

### 25.4. Szyfrowanie PUNCH

Gotowy pakiet jest zwracany przez:

```python
return encrypt_packet(plain)
```

Funkcja `encrypt_packet()` pochodzi z `crypto.py`.

`punch.py` nie implementuje własnego szyfrowania.

Nie wysyła również samodzielnie utworzonego pakietu
przez sieć.

### 25.5. Funkcja validate_punch_ack()

Sygnatura:

```python
def validate_punch_ack(
    packet: bytes,
    expected_did: bytes
) -> bool:
```

Argumenty:

- `packet` — otrzymany pakiet PUNCH_ACK;
- `expected_did` — DID oczekiwanego urządzenia.

Wynikiem jest `True` albo `False`.

Niepoprawny DID przekazany jako argument powoduje
`ValueError`.

### 25.6. Odszyfrowanie odpowiedzi

Funkcja próbuje wykonać:

```python
plain = decrypt_packet(packet)
```

Przechwytuje błędy:

- `ValueError`;
- `TypeError`;
- `IndexError`.

Dla takich błędów odszyfrowywania zwraca `False`.

Nie oznacza to, że wszystkie możliwe wyjątki
są przechwytywane przez tę funkcję.

### 25.7. Warunki poprawnego PUNCH_ACK

Odpowiedź jest akceptowana, jeśli:

1. Odszyfrowane dane mają 24 bajty.
2. `is_valid_ppcs_packet()` akceptuje nagłówek i długość.
3. Typ wiadomości wynosi `0x42`.
4. Bajty od pozycji 4 są identyczne z oczekiwanym DID.

Ostatni warunek:

```python
plain[4:] == expected_did
```

oznacza porównanie 20 bajtów identyfikatora.

### 25.8. Struktura PUNCH_ACK

```text
PUNCH_ACK po odszyfrowaniu:

+----------+----------+--------------+------------------+
| 0xF1     | 0x42     | Długość = 20 | DID              |
| 1 bajt   | 1 bajt   | 2 bajty      | 20 bajtów        |
+----------+----------+--------------+------------------+
```

Sprawdzane jest odzwierciedlenie właściwego DID
w odpowiedzi kamery.

Nie jest to jednak kryptograficzny mechanizm
uwierzytelniania odporny na fałszowanie wiadomości.

### 25.9. Porównanie PUNCH i PUNCH_ACK

| Właściwość | PUNCH | PUNCH_ACK |
|---|---|---|
| Kierunek | Python → kamera | Kamera → Python |
| Typ PPCS | `0x41` | `0x42` |
| DID | Wysyłany | Sprawdzany |
| Szyfrowanie | `encrypt_packet()` | `decrypt_packet()` |
| Moduł | `punch.py` | `punch.py` |

### 25.10. Czego ten moduł nie robi?

`punch.py` nie:

- wysyła pakietów UDP;
- otwiera połączenia sieciowego;
- zarządza liczbą prób;
- odmierza czasu oczekiwania;
- inicjalizuje kanałów DRW;
- odbiera obrazu ani dźwięku.

Tymi zadaniami zajmują się inne części aplikacji.

---

## 26. Moduł transport.py — transmisja UDP dla PUNCH

**Plik:** `src/tosee_b/transport.py`

**Główna funkcja:** `perform_punch()`

**Rola:** wysłanie pakietu PUNCH i oczekiwanie
na poprawną odpowiedź PUNCH_ACK od urządzenia.

### 26.1. Jak współpracują moduły?

```text
live.py
   |
   | perform_punch(sock, address, did)
   v
transport.py
   |
   +-- punch.build_punch_packet(did)
   |
   +-- sock.sendto(packet, address)
   |
   +-- sock.recvfrom(65535)
   |
   +-- punch.validate_punch_ack(response, did)
   |
   v
True / False
```

`transport.py` korzysta z gniazda UDP przekazanego
przez kod wyższego poziomu.

### 26.2. Sygnatura perform_punch()

```python
def perform_punch(
    sock,
    address: tuple[str, int],
    did: bytes,
    timeout: float = 2.0,
    retries: int = 3
) -> bool:
```

Argumenty:

- `sock` — już utworzone gniazdo UDP;
- `address` — adres urządzenia i port;
- `did` — 20-bajtowy identyfikator urządzenia;
- `timeout` — maksymalny czas oczekiwania na jedną próbę;
- `retries` — maksymalna liczba prób.

Domyślne wartości to 2 sekundy na próbę
i maksymalnie 3 próby.

### 26.3. Sprawdzanie argumentów

Kod wymaga, aby:

- `address` było krotką o dwóch elementach;
- port był liczbą całkowitą od 1 do 65535;
- `timeout` było większe od zera;
- `retries` było liczbą całkowitą od 1 do 10.

Funkcja nie sprawdza osobno, czy pierwszy element
adresu jest poprawnym adresem IPv4.

Niepoprawne argumenty powodują `ValueError`.

Poprawność DID jest sprawdzana podczas
wywołania `build_punch_packet()`.

### 26.4. Przygotowanie wiadomości

Przed rozpoczęciem pętli prób wykonywane jest:

```python
packet = build_punch_packet(did)
```

Pakiet jest tworzony tylko raz.

Następnie ten sam zaszyfrowany komunikat
może być wysyłany w kolejnych próbach.

### 26.5. Pętla prób połączenia

Kod wykonuje:

```python
for _ in range(retries):
```

Dla każdej próby:

1. Wyznacza czas graniczny.
2. Wysyła pakiet PUNCH.
3. Oczekuje na odpowiedź UDP.
4. Sprawdza nadawcę i zawartość odpowiedzi.
5. Kończy sukcesem albo kontynuuje oczekiwanie.
6. Po wyczerpaniu limitu może rozpocząć kolejną próbę.

### 26.6. Odmierzanie czasu

Kod używa:

```python
deadline = time.monotonic() + timeout
```

`time.monotonic()` jest zegarem odpowiednim
do odmierzania upływu czasu.

Zmiana daty systemowej nie powinna zaburzyć
odmierzania tego limitu.

Przed kolejnym odbiorem program wyznacza
pozostały czas:

```python
remaining = deadline - time.monotonic()
```

Jeżeli czas się skończył, próba zostaje przerwana.

### 26.7. Wysyłanie UDP

Wiadomość jest wysyłana przez:

```python
sock.sendto(packet, address)
```

W przypadku UDP nie ma tutaj połączenia TCP
ani potwierdzenia transportowego dostarczenia.

Samo wykonanie `sendto()` nie oznacza,
że kamera otrzymała wiadomość.

Właśnie dlatego program oczekuje na PUNCH_ACK.

### 26.8. Odbieranie odpowiedzi

Kod ustawia limit oczekiwania:

```python
sock.settimeout(remaining)
```

Następnie wywołuje:

```python
response, sender = sock.recvfrom(65535)
```

`response` zawiera odebrane bajty.

`sender` zawiera adres i port nadawcy.

Argument `65535` oznacza rozmiar bufora,
do którego funkcja może odebrać datagram.

### 26.9. Sprawdzanie nadawcy

Warunek sukcesu obejmuje:

```python
if sender == address and validate_punch_ack(response, did):
    return True
```

Program wymaga zgodności źródłowego adresu
i portu z oczekiwanym urządzeniem.

Następnie sprawdza treść pakietu PUNCH_ACK.

Niepoprawna odpowiedź z innego adresu nie kończy
próby sukcesem.

### 26.10. Zakończenie powodzeniem

Jeżeli nadejdzie poprawna odpowiedź,
funkcja natychmiast zwraca:

```python
True
```

Nie wysyła wtedy kolejnych pakietów PUNCH.

W `live.py` pozwala to rozpocząć cztery
wymiany sterujące DRW.

### 26.11. Zakończenie niepowodzeniem

Jeżeli żadna próba nie przyniesie poprawnego ACK,
funkcja zwraca:

```python
False
```

`live.py` interpretuje ten wynik jako niepowodzenie:

```python
if not perform_punch(self.sock, self.address, self.did):
    raise TimeoutError("ToSee-B PUNCH failed")
```

Samo `perform_punch()` nie zgłasza tego konkretnego
`TimeoutError` po wyczerpaniu prób.

To rozróżnienie jest ważne przy analizie wyjątków.

### 26.12. Co dzieje się przy niepoprawnych pakietach?

W trakcie pojedynczej próby mogą dotrzeć
datagramy niebędące poprawnym PUNCH_ACK.

Kod je ignoruje i nadal czeka w granicach
ustalonego czasu.

Jeśli `recvfrom()` zgłosi `socket.timeout`,
bieżąca próba zostaje zakończona.

Po wyczerpaniu wszystkich prób wynikiem jest `False`.

Inne wyjątki operacji sieciowych nie są tutaj
ogólnie przechwytywane.

### 26.13. Dlaczego ograniczamy ponawianie prób?

ToSee-B jest urządzeniem akumulatorowym.

Nie chcemy wielokrotnie wykonywać
nieograniczonych prób nawiązania komunikacji
z urządzeniem, które może być uśpione.

W tym module istnieją dwa ograniczenia:

- czas jednej próby;
- maksymalna liczba prób.

Przy wartościach domyślnych całkowity
czas oczekiwania przy braku odpowiedzi wynosi
w przybliżeniu 6 sekund plus narzuty wykonania.

### 26.14. Jak odnosi się to do wersji v14?

Aktualny `event_service.py` uruchamia sesję
dopiero po wykryciu zdarzenia.

Następnie:

```text
Zdarzenie motion / doorbell
          |
          v
event_service.py
          |
          v
av_publisher_v14.py
          |
          v
SafeToSeeBLive.run()
          |
          v
ToSeeBLive.run()
          |
          v
perform_punch()
          |
          v
Cztery wymiany sterujące
          |
          v
Odbiór obrazu i dźwięku
```

W ten sposób mechanizm PUNCH jest częścią
sesji inicjowanej na żądanie.

### 26.15. Czego transport.py nie robi?

Moduł nie:

- realizuje komunikacji przez MQTT;
- publikuje RTSP;
- inicjalizuje kanałów DRW;
- analizuje klatek H.264;
- przechowuje identyfikatorów urządzenia na dysku;
- prowadzi ciągłego procesu ponawiania połączeń.

Zajmuje się wyłącznie ograniczoną czasowo
wymianą PUNCH i PUNCH_ACK.

### 26.16. Podsumowanie dla początkujących

Rozdzielenie odpowiedzialności wygląda tak:

- `punch.py` zna format wiadomości.
- `transport.py` wie, jak wiadomości wysłać i odebrać.
- `live.py` decyduje, kiedy rozpocząć sesję
  oraz co zrobić po poprawnym PUNCH_ACK.

To ułatwia pisanie testów bez fizycznego
uruchamiania kamery.

**Następny moduł do opisania: `reconnect.py`.**


---

## 27. Moduł reconnect.py — zarządzanie kolejnymi sesjami

**Plik:** `src/tosee_b/reconnect.py`

**Główna funkcja:** `run_with_reconnect()`

**Rola:** wykonywanie kolejnych sesji LIVE z kontrolowaną
przerwą między próbami i możliwością zakończenia pętli.

### 27.1. Miejsce w architekturze

```text
Starsza ścieżka transmisji:

runner.run_forever()
        |
        v
reconnect.run_with_reconnect()
        |
        +-- session_factory()
        |        |
        |        v
        |    session.run()
        |        |
        |        v
        |    publisher.publish_session()
        |
        +-- should_stop()
        |
        +-- time.sleep(retry_delay)
```

Uwaga: schemat pokazuje współpracę z `runner.py`.
W tej implementacji `session_factory()` zwraca adapter
`SimpleNamespace`, którego `run` wywołuje
wewnętrzną funkcję uruchamiającą `publish_session()`.

Aktualny `event_service.py` korzysta z
`av_publisher_v14.publish_av_session()` i nie wywołuje
`run_with_reconnect()`.

### 27.2. Sygnatura funkcji

```python
def run_with_reconnect(
    session_factory,
    should_stop,
    retry_delay=3.0
):
```

Argumenty:

- `session_factory` — funkcja zwracająca obiekt sesji
  posiadający metodę `run()`;
- `should_stop` — funkcja zwracająca informację,
  czy należy zakończyć;
- `retry_delay` — przerwa między iteracjami, w sekundach.

Domyślna przerwa wynosi trzy sekundy.

### 27.3. Walidacja retry_delay

```python
if retry_delay < 0:
    raise ValueError("retry_delay must not be negative")
```

Odstęp nie może być ujemny.

Wartość zero jest dopuszczalna.

W takim przypadku kolejne próby mogą następować
bez zamierzonej przerwy między sesjami.

### 27.4. Licznik attempts

```python
attempts = 0
```

Licznik jest zwiększany przy każdym wejściu
do nowej iteracji pętli:

```python
while not should_stop():
    attempts += 1
```

Liczba `attempts` nie oznacza liczby udanych sesji.

Obejmuje również iteracje zakończone obsługiwanym błędem.

### 27.5. Tworzenie i uruchamianie sesji

```python
session = session_factory()
session.run()
```

Program najpierw wywołuje fabrykę sesji.

Następnie wywołuje `run()` na otrzymanym obiekcie.

Dzięki temu `reconnect.py` nie musi znać
szczegółów protokołu kamery ani działania FFmpeg.

Wystarczy, że obiekt posiada odpowiednią metodę.

### 27.6. Obsługa wyjątków

Funkcja przechwytuje:

```python
except (OSError, TimeoutError, ValueError, RuntimeError):
```

Po takim błędzie ponownie sprawdza `should_stop()`.

Jeżeli zwraca `True`, pętla zostaje przerwana.

W przeciwnym razie po zakończeniu bloku `except`
program może przejść do następnej iteracji.

Inne wyjątki nie są w tej funkcji przechwytywane.

### 27.7. Przerwa między sesjami

```python
if not should_stop():
    time.sleep(retry_delay)
```

Przerwa następuje zarówno po obsługiwanym błędzie,
jak i po normalnym zakończeniu sesji, o ile
warunek zatrzymania nadal jest fałszywy.

`time.sleep()` zatrzymuje bieżący wątek
na wskazaną liczbę sekund.

Nie uruchamia osobnego procesu ani zadania w tle.

### 27.8. Kiedy pętla się kończy?

Pętla kończy działanie, gdy funkcja `should_stop()`
zwróci `True`.

Może to nastąpić:

- przed uruchomieniem kolejnej iteracji;
- po obsługiwanym błędzie;
- po zakończeniu sesji, przed kolejną przerwą.

Funkcja nie ustala samodzielnie maksymalnej
liczby prób.

Po zakończeniu zwraca `attempts`.

### 27.9. Zabezpieczenie w runner.py

W `runner.py` zdefiniowano stan:

```python
state = {
    "next_port": config.address[1],
    "failed": False,
}
```

Oraz funkcję:

```python
def guarded_stop():
    return state["failed"] or should_stop()
```

Gdy `publish_session()` zgłosi jeden z obsługiwanych
błędów, `runner.py` ustawia:

```python
state["failed"] = True
```

Przekazany do `run_with_reconnect()` warunek
`guarded_stop()` staje się wtedy prawdziwy.

W efekcie starsza ścieżka kończy pętlę po takim błędzie,
zamiast bez końca ponawiać połączenia z kamerą.

### 27.10. Dlaczego to ważne dla kamery akumulatorowej?

Kamera zasilana akumulatorem może przechodzić
w stan uśpienia.

Nieograniczone ponawianie prób PUNCH byłoby
niepożądane, gdy urządzenie nie odpowiada.

Sama funkcja `run_with_reconnect()` jest ogólnym
mechanizmem ponawiania.

Ochronę przed kolejnymi próbami po błędzie
zapewnia dopiero jej współpraca z `runner.py`.

Nie należy mylić tych dwóch odpowiedzialności.

### 27.11. Różnica między starszą ścieżką i v14

| Element | Starsza ścieżka | Aktualna v14 |
|---|---|---|
| Sterowanie sesjami | `runner.run_forever()` | `event_service.py` |
| Ponawianie | `run_with_reconnect()` | Brak użycia tej funkcji |
| Publikator | `publisher.publish_session()` | `av_publisher_v14.publish_av_session()` |
| Rozpoczęcie | Kolejne sesje według pętli | Po zdarzeniu `motion` lub `doorbell` |
| Ochrona przed równoległą transmisją | Logika starszego runnera | `threading.Lock()` w usłudze |

### 27.12. Czego reconnect.py nie robi?

Ten moduł nie:

- buduje pakietów PUNCH;
- otwiera gniazd UDP;
- wykonuje poleceń DRW;
- odbiera obrazu H.264;
- publikuje MQTT;
- uruchamia FFmpeg;
- samodzielnie zna adresu kamery.

Zarządza wywoływaniem sesji dostarczonych przez
pozostałe części aplikacji.

### 27.13. Podsumowanie dla początkujących

`reconnect.py` pokazuje zastosowanie funkcji
przekazywanych jako argumenty.

`session_factory` odpowiada na pytanie:
„Jak uruchomić kolejną sesję?”.

`should_stop` odpowiada na pytanie:
„Czy należy zakończyć działanie?”.

Dzięki temu ten sam mechanizm może współpracować
z różnymi implementacjami sesji.

**Następny moduł do opisania: `publisher.py`.**


---

## 28. Moduł publisher.py — starszy publikator obrazu RTSP

**Plik:** `src/tosee_b/publisher.py`

**Główna funkcja:** `publish_session()`

**Rola:** uruchomienie pojedynczej sesji ToSee-B i przekazanie
obrazu H.264 do serwera RTSP za pomocą FFmpeg.

### 28.1. Miejsce w architekturze

```text
Starsza ścieżka publikowania:

runner.run_forever()
       |
       v
reconnect.run_with_reconnect()
       |
       v
publisher.publish_session()
       |
       +-- ToSeeBLive.run()
       |        |
       |        v
       |    on_h264(data)
       |        |
       +--------+
                |
                v
         FFmpeg stdin
                |
                | surowy H.264
                v
          RTSP / MediaMTX
```

Aktualny `event_service.py` korzysta z
`av_publisher_v14.py`, a nie z `publisher.py`.

Zachowanie starszego publikatora w repozytorium
pozwala analizować wcześniejszą architekturę.

### 28.2. Funkcja publish_session()

```python
def publish_session(
    address,
    did,
    client_uuid,
    rtsp_url="rtsp://127.0.0.1:8554/tosee",
    duration=3600.0,
    bind_address="0.0.0.0",
    sock=None,
):
```

Argumenty:

| Argument | Znaczenie |
|---|---|
| `address` | Adres i port UDP kamery |
| `did` | 20-bajtowy identyfikator urządzenia |
| `client_uuid` | Identyfikator klienta |
| `rtsp_url` | Docelowy adres publikacji RTSP |
| `duration` | Czas fazy transmisji |
| `bind_address` | Lokalny adres powiązania nowego gniazda |
| `sock` | Opcjonalne istniejące gniazdo UDP |

Domyślny czas sesji wynosi 3600 sekund, czyli godzinę.

Jeśli `duration <= 0`, funkcja zgłasza `ValueError`.

### 28.3. Uruchamianie FFmpeg

Proces jest uruchamiany przez `subprocess.Popen()`.

Najważniejsze argumenty:

```text
-f h264 -r 25 -i pipe:0
-an
-c:v copy
-f rtsp
-rtsp_transport tcp
```

Ich znaczenie:

- `-f h264` — wejście jest surowym strumieniem H.264;
- `-r 25` — deklarowana częstotliwość wejścia 25 FPS;
- `-i pipe:0` — odczyt danych ze standardowego wejścia;
- `-an` — wyłączenie audio;
- `-c:v copy` — przekazywanie wideo bez ponownego kodowania;
- `-f rtsp` — publikacja w formacie RTSP;
- `-rtsp_transport tcp` — użycie TCP jako transportu RTSP.

Opcja `-r 25` jest konfiguracją FFmpeg, a nie pomiarem
rzeczywistej szybkości generowania klatek przez kamerę.

### 28.4. Przekazywanie klatek H.264

Wewnątrz `publish_session()` zdefiniowano callback:

```python
def on_h264(data):
    if ffmpeg.poll() is not None:
        raise RuntimeError("FFmpeg publisher exited")
    ffmpeg.stdin.write(data)
```

Callback to funkcja przekazana do innego obiektu,
która zostanie wywołana po wystąpieniu określonego
zdarzenia.

Tutaj `ToSeeBLive` wywołuje ją po przygotowaniu
odpowiednich danych H.264.

Zanim dane zostaną zapisane, program sprawdza,
czy FFmpeg nadal działa.

Zapis przez `ffmpeg.stdin.write()` odbywa się
bez osobnej kolejki pakietów i bez multipleksera NUT.

### 28.5. Własne lub przekazane gniazdo UDP

Funkcja przewiduje dwa warianty.

**Wariant A: `sock is None`**

Tworzy nowe gniazdo:

```python
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as owned_sock:
    owned_sock.bind((bind_address, 0))
```

Port `0` oznacza automatyczny wybór wolnego portu
lokalnego przez system operacyjny.

Konstrukcja `with` zamyka gniazdo po zakończeniu
odpowiedniego bloku kodu.

**Wariant B: `sock` został przekazany**

Funkcja korzysta z istniejącego gniazda UDP.

Nie otwiera wówczas nowego gniazda i nie zamyka
przekazanego obiektu.

Takie rozwiązanie pozwala `runner.py` współdzielić
jedno gniazdo między kolejnymi sesjami.

### 28.6. Tworzenie klienta ToSeeBLive

W obu wariantach wykorzystywany jest:

```python
client = ToSeeBLive(
    sock=sock,
    address=address,
    did=did,
    client_uuid=client_uuid,
    on_h264=on_h264,
)
```

W wariancie własnego gniazda argument `sock`
ma wartość lokalnej zmiennej `owned_sock`.

Brak argumentu `on_audio` oznacza wykorzystanie
domyślnej wartości `None` w konstruktorze `ToSeeBLive`.

Dlatego ten publikator nie przekazuje ścieżki audio.

### 28.7. Uruchomienie sesji i statystyki

Właściwa sesja rozpoczyna się przez:

```python
stats = client.run(duration=duration)
```

Po jej zakończeniu program ponownie sprawdza,
czy FFmpeg nie zakończył pracy.

Następnie zwraca `stats`, czyli obiekt `LiveStats`
pochodzący z modułu `live.py`.

Funkcja nie implementuje samodzielnie ponawiania
sesji. Odpowiedzialność ta należy do wywołującego.

### 28.8. Zamykanie procesu FFmpeg

Blok `finally` jest wykonywany zarówno przy sukcesie,
jak i przy zgłoszeniu wyjątku.

Jeżeli proces FFmpeg został utworzony:

1. Program próbuje zamknąć jego `stdin`.
2. Ignoruje `BrokenPipeError` przy tej operacji.
3. Czeka maksymalnie 10 sekund na zakończenie procesu.
4. Jeśli limit minie, wykonuje `ffmpeg.kill()`.
5. Oczekuje na zakończenie zabitego procesu.

Istotne: ta wersja nie zawiera osobnego mechanizmu
weryfikacji końcowego kodu wyjścia FFmpeg po `wait()`.

Nie obsługuje również oddzielnego wątku
multipleksera, ponieważ nie używa PyAV/NUT.

### 28.9. Różnice względem av_publisher_v14.py

| Cecha | `publisher.py` | `av_publisher_v14.py` |
|---|---|---|
| Wideo | H.264 | H.264 |
| Audio | Brak | G.711 A-law |
| Wejście FFmpeg | Surowy H.264 | NUT |
| PyAV | Nie | Tak |
| Osobna kolejka | Nie | Tak, do 512 elementów |
| Wątek multipleksera | Nie | Tak |
| Ustawienie FPS | 25 | 20 |
| Własne gniazdo UDP | Opcjonalne | Tak |
| Domyślny RTSP | `/tosee` | `/tosee-av-test` |
| Domyślny czas sesji | 3600 s | 60 s |
| Wywoływany przez aktualną usługę | Nie | Tak |

W aktualnym `event_service.py` publikator v14
otrzymuje `duration=120.0`.

### 28.10. Dlaczego zachowujemy starszy moduł?

`publisher.py` pokazuje prostsze rozwiązanie:
bezpośredni zapis H.264 do FFmpeg.

Wersja v14 rozszerza tę architekturę o audio,
kolejkę, znaczniki czasowe i multipleksowanie.

Obecność starszego pliku w repozytorium nie oznacza,
że jest on jednocześnie uruchamiany z wersją v14.

Ważne jest sprawdzenie, który moduł jest rzeczywiście
importowany i wywoływany przez usługę systemd.

### 28.11. Podsumowanie dla początkujących

W `publisher.py` dobrze widać rozdzielenie zadań:

- `ToSeeBLive` odbiera i przygotowuje obraz.
- `on_h264()` przekazuje go do FFmpeg.
- FFmpeg publikuje strumień RTSP.
- `runner.py` może zarządzać kolejnymi sesjami.

Moduł nie zajmuje się wykrywaniem dzwonka ani MQTT.

**Następny etap:** analiza pozostałych wariantów
`av_publisher.py`, `av_publisher_debug.py`
i historycznych wersji v10–v13.


---

## 29. Historia rozwoju publikatorów audio i wideo

Ten rozdział opisuje rozwój mechanizmu publikowania
transmisji ToSee-B na podstawie porównania kodu
kolejnych wariantów.

Nie wszystkie warianty są uruchamiane produkcyjnie.

**Aktualna usługa `event_service.py` wykorzystuje
`av_publisher_v14.py`.**

### 29.1. Dlaczego w repozytorium jest kilka publikatorów?

Podczas rozwoju projektu powstawały kolejne
implementacje transmisji audio i wideo.

Zachowano je w osobnych plikach, aby umożliwić:

- porównywanie rozwiązań;
- analizowanie wcześniejszych eksperymentów;
- sprawdzanie zmian w synchronizacji mediów;
- odtwarzanie przyczyn problemów;
- testowanie różnych sposobów przekazywania danych.

Sama obecność pliku w katalogu `src/tosee_b/`
nie oznacza, że moduł jest uruchamiany.

O uruchamianiu decydują importy i wywołania
w kodzie punktu wejścia usługi.

### 29.2. Zestawienie wariantów

| Plik | Charakterystyczne rozwiązanie |
|---|---|
| `av_publisher.py` | Oddzielne ścieżki audio i wideo |
| `av_publisher_debug.py` | Diagnostyka i tolerowanie wybranych błędów audio |
| `av_publisher_v10.py` | Powiększanie potoku audio, parametry analizy FFmpeg |
| `av_publisher_v11.py` | Parametry przeplatania i opróżniania pakietów |
| `av_publisher_v12.py` | Liczniki zapisów i diagnostyka potoku |
| `av_publisher_v13.py` | Wspólny kontener NUT i multiplekser PyAV |
| `av_publisher_v14.py` | Korekta znaczników czasu audio o -300 ms |

Osobnym modułem jest `publisher.py`, opisany
w rozdziale 28. Publikuje on wyłącznie wideo H.264.

### 29.3. Pierwszy av_publisher.py

Wariant podstawowy wykorzystuje oddzielne
ścieżki przekazywania obrazu i dźwięku.

W porównaniu kodu widoczne są:

- `os.pipe()` dla audio;
- osobne kolejki `video_queue` i `audio_queue`;
- wątki zapisujące dane;
- FFmpeg otrzymujący obraz H.264 i audio A-law
  jako dwa osobne wejścia.

To przykład rozwiązania, w którym program musi
zarządzać kilkoma źródłami danych równolegle.

### 29.4. av_publisher_debug.py

W tej wersji dodano klasę:

```python
class SafeToSeeBLive(ToSeeBLive):
```

Przechwytuje ona wybrane błędy audio,
aby nie przerywać sesji dla rozpoznanych
nieprawidłowych pakietów.

Wprowadzono również:

- zmianę poziomu logów FFmpeg z `error` na `info`;
- zmianę deklarowanej częstotliwości obrazu z 25 na 20;
- przekazywanie diagnostyki FFmpeg na standardowe stderr.

W tej wersji pojawia się tekst błędu:

`Invalid ToSee-B audio payload header`

Nie odpowiada on komunikatowi obecnego `audio.py`:

`Invalid ToSee-B audio frame header`

Ta różnica została poprawiona w kolejnym wariancie.

### 29.5. av_publisher_v10.py

Wersja v10 dodaje:

```python
fcntl.fcntl(
    audio_write,
    fcntl.F_SETPIPE_SZ,
    1048576,
)
```

Jest to próba ustawienia pojemności potoku audio
na 1 MiB.

Rzeczywisty sukces tej operacji zależy od
ograniczeń i uprawnień systemu Linux.

W parametrach FFmpeg dla obu wejść dodano:

```text
-probesize 32768
-analyzeduration 100000
```

Zmiany dotyczą przygotowania potoków i sposobu,
w jaki FFmpeg analizuje przychodzące media.

Poprawiono także nazwę rozpoznawanego błędu audio.

### 29.6. av_publisher_v11.py

Porównanie v10 i v11 ujawnia tylko
dwie dodatkowe opcje FFmpeg:

```text
-max_interleave_delta 100000
-flush_packets 1
```

Pierwsza dotyczy ograniczenia czasu
przeplatania pakietów różnych strumieni.

Druga żąda opróżniania pakietów wyjściowych.

Na podstawie samego kodu nie można stwierdzić,
jak duża była rzeczywista poprawa synchronizacji.

### 29.7. av_publisher_v12.py

Wersja v12 rozszerza instrumentację diagnostyczną.

Dodano między innymi:

```python
diagnostic_start = time.monotonic()
diagnostic_counts = {"video": 0, "audio": 0}
diagnostic_lock = threading.Lock()
```

Program rejestruje:

- moment pierwszego zapisu danych każdego rodzaju;
- liczbę zapisanych bajtów audio;
- liczbę zapisanych bajtów wideo;
- ilość nieodczytanych danych w potoku audio;
- łączny czas wykonania.

Komunikaty obejmują:

```text
V12_FIRST_WRITE
V12_PIPE_AUDIO
V12_BYTES_WRITTEN
```

Do sprawdzenia potoku wykorzystywane są:

```python
fcntl.ioctl(
    audio_write,
    termios.FIONREAD,
    unread,
    True,
)
```

Jest to przykład diagnostyki, która pozwala
obserwować działanie potoków systemu Linux.

### 29.8. Przejście v12 → v13

To największa widoczna zmiana architektury
w analizowanej serii.

Wcześniejsze wersje wykorzystywały dwa
oddzielne wejścia FFmpeg dla mediów.

Wersja v13 wprowadza PyAV i kontener NUT.

Nowy przepływ danych:

```text
ToSeeBLive
   |
   +-- H.264 --+
   |           |
   +-- A-law --+
               |
               v
       Wspólna kolejka
               |
               v
          PyAV / NUT
               |
               v
        Jeden potok
               |
               v
            FFmpeg
               |
               v
         RTSP / MediaMTX
```

W kodzie pojawia się:

```python
packets = queue.Queue(maxsize=512)
```

Dane audio i wideo trafiają do wspólnej kolejki.

Osobny wątek multipleksera przypisuje im
znaczniki czasowe PTS i DTS.

Kontener NUT dostarcza FFmpeg oba strumienie
przez jedno wejście `pipe:0`.

Taka architektura ogranicza konieczność
niezależnego zarządzania dwoma wejściami FFmpeg.

Nie stanowi jednak automatycznej gwarancji
idealnej synchronizacji mediów.

### 29.9. Przejście v13 → v14

Porównanie kodu wskazuje dokładnie
dwa zmienione fragmenty.

Dodano:

```python
audio_offset_ms = -300
audio_offset_pts = round(audio_offset_ms * 8)
```

Oraz zmieniono:

```python
pkt.pts = pkt.dts = audio_pts + audio_offset_pts
```

W wersji v13 stosowano:

```python
pkt.pts = pkt.dts = audio_pts
```

Skala czasowa audio wynosi 8000 jednostek
na sekundę, czyli 8 jednostek na milisekundę.

Dlatego korekta wynosi:

```text
-300 ms × 8 = -2400 jednostek PTS/DTS
```

Nie zmienia ona zawartości próbek audio.

Modyfikuje jedynie ich położenie na osi czasu
przekazywanej do multipleksera.

### 29.10. Co zostało zachowane między v13 i v14?

Na podstawie porównania obu plików
pozostałe fragmenty kodu są identyczne.

Zachowano między innymi:

- klasę `SafeToSeeBLive`;
- kolejkę o pojemności 512 elementów;
- osobny wątek multipleksera;
- kontener NUT;
- strumienie H.264 i G.711 A-law;
- proces FFmpeg;
- mechanizmy zamykania transmisji.

Dlatego v14 jest niewielką modyfikacją v13
na poziomie kodu, mimo istotnego znaczenia
korekty czasu audio.

### 29.11. Dlaczego w v14 występują napisy V13?

W aktualnym kodzie nadal występują:

```text
V13_FIRST_MUX
V13_MUX_COUNTS
```

Są to etykiety komunikatów diagnostycznych
pozostawione z wcześniejszej wersji.

Nie oznacza to, że `event_service.py`
uruchamia publikator v13.

O używanej implementacji decyduje import:

```python
from .av_publisher_v14 import publish_av_session
```

### 29.12. Jak odróżniać testowy kod od produkcyjnego?

Najważniejsze miejsca do sprawdzenia:

1. Plik `tosee-b.service` i jego `ExecStart`.
2. Moduł uruchamiany przez parametr `-m`.
3. Importy w `event_service.py`.
4. Funkcja uruchamiająca transmisję.
5. Adres RTSP przekazywany do publikatora.

W analizowanym środowisku systemd uruchamia
`event_service.py`, który korzysta z v14.

Wariantów historycznych nie należy uruchamiać
równocześnie z działającą usługą bez
osobnego, przemyślanego planu testowego.

### 29.13. Lekcje programistyczne

Historia publikatorów pokazuje kilka ważnych zasad:

**Rozdzielenie odpowiedzialności**

Odbieranie pakietów z kamery i publikowanie RTSP
są obsługiwane przez różne moduły.

**Diagnostyka przed zmianami architektury**

Wersja v12 zawiera rozbudowane liczniki i pomiary,
które pomagają obserwować przepływ danych.

**Ograniczone kolejki**

Limity pojemności chronią przed niekontrolowanym
wzrostem zużycia pamięci.

**Synchronizacja multimediów**

Poprawny obraz i poprawny dźwięk nie oznaczają
automatycznie zgodności ich znaczników czasu.

**Zachowanie historii**

Osobne pliki wariantów umożliwiają porównanie
implementacji i zrozumienie ewolucji projektu.

### 29.14. Co pozostaje niepotwierdzone?

Samo porównanie kodu nie dowodzi:

- wyników wszystkich wcześniejszych prób;
- rzeczywistego wpływu każdego parametru FFmpeg;
- przyczyny wyboru konkretnych wartości limitów;
- zgodności wariantów z innymi kamerami;
- przydatności starszych wersji w aktualnym środowisku.

Takie informacje wymagają dodatkowych dzienników
testowych albo pomiarów.

### 29.15. Podsumowanie

Dla nowej osoby rozpoczynającej pracę z projektem
najważniejszy jest `av_publisher_v14.py`.

Pozostałe warianty służą przede wszystkim
zrozumieniu historii rozwoju i wcześniejszych
podejść do transmisji audio/wideo.

**Kolejny moduł: `event_service_v14.py`.**


---

## 30. Moduł event_service_v14.py — zachowana kopia usługi

**Plik:** `src/tosee_b/event_service_v14.py`

**Rozmiar:** 96 linii.

**Rola:** zachowana kopia implementacji usługi obsługującej
zdarzenia ToSee-B, publikację MQTT i transmisję RTSP v14.

### 30.1. Najważniejsze ustalenie

Bezpośrednie porównanie plików:

```bash
cmp -s \
  src/tosee_b/event_service.py \
  src/tosee_b/event_service_v14.py
```

potwierdziło, że oba pliki są identyczne.

Wynik kontroli:

```text
EVENT_SERVICES_IDENTICAL
```

Nie występują między nimi różnice w kodzie.

### 30.2. Dlaczego warto o tym wiedzieć?

Nazwy plików mogłyby sugerować dwie odmienne
implementacje usługi.

W rzeczywistości analizowana wersja obu modułów
zawiera te same funkcje, importy i ustawienia.

Aktualna usługa systemd uruchamia:

```text
python -u -m tosee_b.event_service
```

Z odpowiednim argumentem `--env-file`.

Nie uruchamia `tosee_b.event_service_v14`.

Dlatego zmiana wyłącznie pliku `event_service_v14.py`
nie wpłynęłaby na aktualnie skonfigurowaną usługę.

### 30.3. Importowane moduły

Oba pliki zawierają:

```python
from .event_listener import listen_events
from .mqtt_events import publish_event
from .av_publisher_v14 import publish_av_session
from .runner import load_config
```

Każdy import ma osobne zadanie:

- `listen_events` — dostarczanie wykrytych zdarzeń;
- `publish_event` — wysyłanie zdarzeń do MQTT;
- `publish_av_session` — uruchamianie transmisji AV;
- `load_config` — odczyt konfiguracji połączenia.

### 30.4. Funkcja load_env_file()

Funkcja czyta wskazany plik tekstowy.

Pomija puste linie oraz komentarze rozpoczynające
się od `#`.

Pozostałe linie dzieli na nazwę ustawienia
i wartość według pierwszego znaku `=`.

Nie wykonuje zawartości pliku jako poleceń powłoki.

Nie jest to jednak pełny parser wszystkich
możliwych składni plików `.env`.

### 30.5. Funkcja main()

Funkcja `main()`:

1. Odczytuje argument `--env-file`.
2. Wczytuje ustawienia.
3. Tworzy blokadę `threading.Lock()`.
4. Rozpoczyna iterowanie po zdarzeniach.
5. Publikuje otrzymane zdarzenie w MQTT.
6. Dla `motion` lub `doorbell` próbuje uruchomić wideo.
7. Nie uruchamia drugiej sesji, gdy blokada jest zajęta.

Obsługuje również `KeyboardInterrupt`
w głównej pętli zdarzeń.

### 30.6. Funkcja wewnętrzna run_video()

Funkcja `run_video()` została zdefiniowana
wewnątrz `main()`.

Pobiera ustawienia połączenia przez `load_config()`
i uruchamia:

```python
publish_av_session(
    address=config.address,
    did=config.did,
    client_uuid=config.client_uuid,
    rtsp_url="rtsp://127.0.0.1:8554/tosee-av-test",
    duration=120.0,
)
```

Oznacza to:

- publikację na ścieżce RTSP `/tosee-av-test`;
- czas fazy transmisji równy 120 sekund;
- wykorzystanie publikatora v14.

Błędy są wypisywane do logu, a blokada wideo
zwalniana w bloku `finally`.

### 30.7. Kolejność MQTT i wideo

Kod najpierw wykonuje:

```python
publish_event(event.kind, environ=settings)
```

Dopiero potem podejmuje próbę uruchomienia
wątku transmisji.

Jeżeli publikowanie MQTT zgłosi wyjątek,
kod nie przechodzi do uruchamiania wideo
dla tego zdarzenia.

Właściwa obsługa wideo odbywa się
w osobnym wątku `daemon=True`.

### 30.8. Ochrona przed równoległymi sesjami

Kod wykorzystuje:

```python
video_lock.acquire(blocking=False)
```

Jeżeli blokada jest zajęta, nowa sesja
nie zostaje uruchomiona.

Program wypisuje wtedy:

```text
TOSEE_VIDEO_ALREADY_RUNNING
```

Publikacja MQTT następuje jednak wcześniej,
więc drugie zdarzenie może zostać zgłoszone
bez uruchomienia kolejnego strumienia RTSP.

### 30.9. Historyczna domyślna ścieżka konfiguracji

W obu plikach pozostawiono historyczną wartość
`DEFAULT_ENV_FILE` wskazującą dawną lokalizację
projektu.

W aktualnej usłudze używany jest jawny argument:

```text
--env-file /home/tosee/.tosee.env
```

W dokumentacji nie publikujemy zawartości
tego pliku ani zapisanych w nim haseł.

### 30.10. Czy należy usuwać jedną z kopii?

Nie jest to konieczne do działania systemu.

W ramach prac dokumentacyjnych nie zmieniamy
ani nie usuwamy żadnego modułu.

Ewentualne porządkowanie kodu powinno nastąpić
osobno, po sprawdzeniu wszystkich odwołań
i odpowiednich testach.

### 30.11. Podsumowanie dla początkujących

Najważniejsze jest rozróżnienie:

- nazwa pliku nie przesądza o jego aktywności;
- identyczne pliki mogą mieć różne role organizacyjne;
- rzeczywisty punkt wejścia ustala konfiguracja systemd;
- aktualna transmisja korzysta z `av_publisher_v14.py`.

Szczegółowy opis działania usługi znajduje się
we wcześniejszym rozdziale dotyczącym
`event_service.py`.

**Następny etap:** przegląd testów automatycznych,
a następnie audyt całej dokumentacji.


---

## 31. Testy automatyczne projektu ToSee-B

Testy automatyczne znajdują się w katalogu `tests/`.

Ich zadaniem jest sprawdzanie wybranych zachowań
programu bez konieczności ręcznego powtarzania
wszystkich scenariuszy.

### 31.1. Framework unittest

Projekt korzysta z biblioteki `unittest`,
która należy do standardowej biblioteki Pythona.

Przykładowa struktura testu:

```python
import unittest

class ExampleTests(unittest.TestCase):
    def test_example(self):
        self.assertEqual(2 + 2, 4)
```

`TestCase` reprezentuje klasę zawierającą testy.

Metody rozpoczynające się od `test_` są
odnajdywane i wykonywane przez mechanizm testowy.

`assertEqual()` porównuje wartość rzeczywistą
z oczekiwaną.

### 31.2. Prawidłowe uruchamianie testów

Repozytorium korzysta z układu katalogów `src/`.

Dlatego podczas uruchamiania testów
należy udostępnić interpreterowi ten katalog.

Z katalogu głównego projektu:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover \
    -s tests -p 'test_*.py' -q
```

W analizowanym środowisku polecenie jest wykonywane
z uprawnieniami użytkownika `tosee`:

```bash
runuser -u tosee -- env PYTHONPATH=src \
    .venv/bin/python -m unittest discover \
    -s tests -p 'test_*.py' -q
```

### 31.3. Dlaczego potrzebny jest PYTHONPATH?

Kod aplikacji znajduje się w:

```text
src/tosee_b/
```

Natomiast testy importują moduły jako:

```python
from tosee_b.ack import build_drw_ack
```

Jeżeli interpreter nie odnajdzie katalogu `src`,
może zgłosić:

```text
ModuleNotFoundError: No module named 'tosee_b'
```

Nie oznacza to automatycznie błędu implementacji
funkcji `build_drw_ack()`.

Jest to problem z lokalizacją pakietu Pythona
w danym sposobie uruchomienia.

### 31.4. Potwierdzony wynik testów

Po ustawieniu `PYTHONPATH=src` uzyskano:

```text
Ran 159 tests in 3.799s

OK
```

Oznacza to, że podczas tego uruchomienia
159 testów zakończyło się pomyślnie.

Wcześniejsze uruchomienie bez `PYTHONPATH=src`
zgłosiło trzy błędy importu.

### 31.5. Testy PPCS i kryptografii

Najważniejsze pliki:

- `test_crypto.py`;
- `test_punch.py`;
- `test_transport.py`;
- `test_drw.py`;
- `test_ack.py`;
- `test_commands.py`;
- `test_session.py`.

Sprawdzane scenariusze obejmują między innymi:

- poprawność nagłówków i długości PPCS;
- szyfrowanie oraz odszyfrowywanie danych;
- zgodność identyfikatora DID;
- akceptowanie i odrzucanie odpowiedzi PUNCH_ACK;
- ograniczenia liczby prób;
- struktury wiadomości DRW;
- inicjalizację i potwierdzenia sesji.

### 31.6. Testy odbioru LIVE

Pliki:

- `test_live.py`;
- `test_live_audio.py`;
- `test_live_f0.py`.

Obejmują scenariusze związane z:

- odpowiedziami na polecenia sterujące;
- odbieraniem obrazu;
- odbieraniem dźwięku;
- wysyłaniem potwierdzeń;
- odrzucaniem pakietów od niewłaściwego nadawcy;
- limitami czasu;
- zamykaniem sesji.

### 31.7. Testy H.264 i kolejności pakietów

W katalogu znajdują się między innymi:

- `test_video.py`;
- `test_video_sync.py`;
- `test_video_sequence.py`;
- `test_video_reorder.py`;
- `test_video_reorder_integration.py`;
- `test_video_recovery.py`;
- `test_video_gap_recovery.py`;
- `test_video_keyframe_recovery.py`;
- `test_live_reorder.py`.

Sprawdzają one scenariusze związane z:

- niekompletnymi klatkami H.264;
- pakietami docierającymi w złej kolejności;
- powtarzającymi się pakietami;
- przepełnieniem 16-bitowego numeru sekwencyjnego;
- brakującymi i opóźnionymi pakietami;
- odrzucaniem uszkodzonych danych;
- oczekiwaniem na klatkę kluczową;
- wznowieniem poprawnej synchronizacji obrazu.

`test_live_reorder.py` jest jednym z najbardziej
rozbudowanych plików testowych projektu.

### 31.8. Testy audio

`test_audio.py` sprawdza między innymi:

- pojedynczą ramkę;
- kilka kolejnych ramek;
- nieprawidłowy rozmiar;
- nieprawidłowy nagłówek;
- pusty pakiet;
- nieprawidłowy typ argumentu.

Testy te dotyczą wyodrębniania danych A-law
z formatu ramek ToSee-B.

### 31.9. Testy publikatorów

Najważniejsze pliki:

- `test_publisher.py`;
- `test_publisher_shared_socket.py`;
- `test_av_publisher.py`.

Weryfikują wybrane scenariusze:

- uruchomienie sesji publikatora;
- przekazywanie danych H.264;
- przekazywanie audio do potoku;
- zachowanie współdzielonego gniazda;
- reakcję na błędy FFmpeg;
- zamknięcie lub zabicie procesu;
- poprawność ograniczeń czasu sesji;
- zapis częściowy do potoku;
- sytuację pełnego potoku audio.

Uwaga: `test_av_publisher.py` importuje moduł
`av_publisher.py`, a nie `av_publisher_v14.py`.

Dlatego przejście tych testów nie oznacza
automatycznie bezpośredniego przetestowania
wszystkich szczegółów publikatora v14.

### 31.10. Testy zdarzeń i MQTT

Pliki:

- `test_event_listener.py`;
- `test_event_service.py`;
- `test_mqtt_events.py`.

Obejmują między innymi:

- rozpoznawanie `motion` i `doorbell`;
- ignorowanie niepowiązanych pakietów;
- deduplikację zdarzeń;
- wczytywanie konfiguracji;
- wartości zawierające znak `=`;
- poprawność tematów MQTT;
- reakcje na błędne ustawienia połączenia.

### 31.11. Testy runnera i ponawiania sesji

Pliki:

- `test_runner.py`;
- `test_runner_ports.py`;
- `test_reconnect.py`;
- `test_reconnect_publisher.py`.

Sprawdzają między innymi:

- poprawność konfiguracji;
- walidację DID i portów;
- wywoływanie publikatora;
- współdzielenie gniazda UDP;
- zachowanie po błędzie sesji;
- kolejne próby połączenia;
- zatrzymywanie pętli.

### 31.12. Czym jest mock?

`unittest.mock` pozwala zastąpić prawdziwy
obiekt kontrolowaną atrapą podczas testu.

Przykładowo, zamiast uruchamiać prawdziwy proces
FFmpeg, test może sprawdzić, z jakimi argumentami
program próbowałby go uruchomić.

Przykład:

```python
from unittest.mock import MagicMock

process = MagicMock()
process.poll.return_value = None
```

Dzięki temu można badać logikę aplikacji
bez wymagania działającego procesu FFmpeg.

### 31.13. Czym różni się test jednostkowy
od testu integracyjnego?

**Test jednostkowy** sprawdza niewielki element
programu w możliwie kontrolowanych warunkach.

**Test integracyjny** sprawdza współpracę
kilku elementów.

Nazwy plików testowych mogą używać określenia
`integration`, ale dokładny zakres testu
wynika z jego implementacji.

Nie należy zakładać, że każdy test integracyjny
kontaktuje się z fizyczną kamerą.

### 31.14. Czego pozytywny wynik nie gwarantuje?

Wynik `OK` nie potwierdza automatycznie:

- dostępności rzeczywistej kamery;
- jakości sygnału sieciowego;
- poprawnego wybudzania urządzenia;
- idealnej synchronizacji audio i wideo;
- poprawnej konfiguracji MediaMTX;
- odtwarzania transmisji przez Home Assistant;
- braku błędów w scenariuszach nieobjętych testami.

Testy automatyczne są niezbędnym elementem
kontroli jakości, ale nie zastępują testów
z rzeczywistym sprzętem.

### 31.15. Dobre praktyki podczas rozwoju

Po zmianie kodu warto:

1. Uruchomić odpowiednie testy jednostkowe.
2. Uruchomić cały zestaw testów.
3. Sprawdzić regresje w modułach zależnych.
4. Dopiero później rozważać test ze sprzętem.
5. Nie uruchamiać równoległej sesji kamery
   bez świadomego planu diagnostycznego.

W tym projekcie szczególną uwagę należy
zwracać na oszczędzanie akumulatora kamery
i unikanie niepotrzebnych prób PUNCH.

### 31.16. Podsumowanie dla początkujących

Testy pokazują, jak sprawdzić działanie programu
bez wykonywania każdej operacji ręcznie.

Dla osoby rozpoczynającej naukę Pythona
dobrym punktem wyjścia są:

- `test_audio.py`;
- `test_punch.py`;
- `test_ack.py`;
- `test_transport.py`.

Następnie warto przejść do bardziej złożonych
testów LIVE, porządkowania pakietów i odzyskiwania
obrazu po utracie danych.

**Następny etap:** końcowy audyt dokumentacji.
