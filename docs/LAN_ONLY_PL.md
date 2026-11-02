# ToSee-B LAN-Only + Home Assistant TALK V2

## Cel

Ta wersja projektu umożliwia lokalną obsługę dzwonka ToSee-B
bez komunikacji z serwerami producenta.

Przetestowana instalacja wykorzystuje Home Assistant,
MediaMTX, MQTT, Caddy oraz Fully Kiosk Browser.

## Izolacja sieciowa

Dzwonek ma adres 192.168.1.138 w przetestowanej sieci LAN.
Jego połączenia do WAN są blokowane na routerze.

Adresy IP i reguły zapory należy dopasować do własnej instalacji.

## Wykrywanie naciśnięcia dzwonka

Starszy detektor rozpoznawał pakiety UDP z ładunkiem
1104 bajtów, kierowane do portów 15000 lub 25000.

Detektor LAN rozpoznaje pakiety UDP z ładunkiem 16 bajtów,
kierowane na port 32700.

Filtr tcpdump wykorzystuje wartość 24 w polu długości UDP:
8 bajtów nagłówka UDP + 16 bajtów danych.

Zmiana dotyczy detekcji ruchu sieciowego po stronie serwera,
a nie modyfikacji firmware'u dzwonka.

## Obsługa zdarzenia

Skrypt scripts/tosee-lan-doorbell.py obserwuje ruch
za pomocą tcpdump uruchamianego zdalnie przez SSH.

Po wykryciu naciśnięcia:

1. Wysyła DOORBELL przez Unix socket.
2. Serwer rejestruje zdarzenie w TalkSession.
3. Uruchamia istniejącą transmisję LIVE.
4. Detektor publikuje zdarzenie MQTT.

Unix socket: /run/tosee-b/live.sock

## TALK V2

TALK V2 korzysta z WebSocket oraz autoryzacji Home Assistant.

W przetestowanej instalacji Caddy obsługuje HTTPS i WSS.

Funkcja rozmowy jest dostępna po zarejestrowaniu
naciśnięcia dzwonka oraz uzyskaniu gotowości LIVE.

Obowiązuje dodatkowe opóźnienie 4 sekund.

## Potwierdzone działanie

Stan na 2 listopada 2026:

- Wykrywanie naciśnięcia dzwonka w LAN.
- Uruchamianie LIVE.
- Publikacja zdarzeń MQTT.
- TALK V2 w Microsoft Edge.
- TALK V2 w Fully Kiosk Browser.
- Transmisja mikrofonu tabletu do głośnika dzwonka.
- Poprawne wyświetlanie HA po restarcie Fully Kiosk Browser.

## Bezpieczeństwo

Nie publikuj pliku .tosee.env, haseł MQTT,
tokenów Home Assistant, prywatnych kluczy TLS,
danych uwierzytelniających urządzenia ani zrzutów
ruchu sieciowego mogących zawierać poufne informacje.

Lokalne adresy IP są przykładami z instalacji testowej.

## Ograniczenia

To rozwiązanie jest eksperymentalne i zostało
przetestowane na określonym modelu ToSee-B.

Wymaga poprawnej konfiguracji LAN, SSH, MQTT,
MediaMTX, Home Assistant i serwera TALK V2.

Nie gwarantuje identycznego działania na innych
wersjach firmware'u ani innych modelach sprzętu.
