# To-Do-Backend mit Telegram-Eingabe und E-Ink-Anzeige

Aufgaben werden unterwegs per Telegram erfasst und am Schreibtisch auf einem
M5Paper (ESP32, 960×540 E-Ink) angezeigt und abgehakt.

Dieses Verzeichnis enthält **nur das Backend** plus eine Web-Attrappe des
Displays. Kein ESP32-Code — das Gerät kommt später, das Backend ist ohne
Hardware vollständig benutzbar.

## Aufbau

```
app/config.py    Umgebungsvariablen
app/db.py        SQLite über das sqlite3-Modul, Schema per CREATE TABLE IF NOT EXISTS
app/display.py   Payload für das Gerät: kürzen, Alter, Versions-Hash
app/api.py       /api-Routen, alle hinter X-API-Key
app/telegram.py  Long-Polling-Poller und die reine Verarbeitungsfunktion
app/main.py      App, Lifespan, /healthz, /display
app/static/      Web-Attrappe des Displays
tests/           pytest gegen den FastAPI-TestClient
```

## Einrichtung

### 1. Bot beim BotFather anlegen

1. In Telegram [@BotFather](https://t.me/BotFather) anschreiben.
2. `/newbot`, dann Name und Benutzername vergeben (der Benutzername muss auf
   `bot` enden).
3. Der BotFather antwortet mit dem Token in der Form
   `123456789:AAE...`. Das ist `TELEGRAM_TOKEN`.

### 2. Konfiguration anlegen

```bash
cp .env.example .env
# API_KEY setzen, z. B.:
openssl rand -hex 24
```

`TELEGRAM_CHAT_ID` bleibt zunächst auf `0`.

### 3. Eigene Chat-ID herausfinden

`TELEGRAM_CHAT_ID=0` ist der Einrichtungsmodus: eingehende Nachrichten werden
nicht verarbeitet, die Chat-ID landet nur im Log.

```bash
docker compose up -d
# Jetzt dem eigenen Bot in Telegram irgendetwas schreiben, dann:
docker compose logs -f todo
```

Im Log steht dann:

```
INFO todo.telegram TELEGRAM_CHAT_ID ist nicht gesetzt. Eingehende Chat-ID: 123456789
```

Diese Zahl in `.env` als `TELEGRAM_CHAT_ID` eintragen und neu starten:

```bash
docker compose up -d --force-recreate
```

Ab jetzt werden nur noch Nachrichten aus diesem Chat verarbeitet, alle anderen
werden ignoriert.

## Starten

```bash
docker compose up -d          # http://localhost:8000
docker compose logs -f todo
```

Die Datenbank liegt im Volume `todo-data` unter `/data/tasks.db` und übersteht
`docker compose down`.

Ohne Docker:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
set -a && source .env && set +a
DB_PATH=./tasks.db .venv/bin/uvicorn app.main:app --reload
```

## Bedienung per Telegram

| Eingabe | Wirkung |
|---|---|
| Freitext | legt eine Aufgabe an |
| mehrzeiliger Text | eine Aufgabe pro Zeile |
| `/list` | offene Aufgaben, durchnummeriert |
| `/done <Nummer>` | hakt die Aufgabe mit dieser Nummer ab |
| `/help` | Kurzhilfe |

Die Nummern von `/done` beziehen sich auf die Position in der Liste der offenen
Aufgaben, nicht auf die Datenbank-ID. Nach einem `/done` verschieben sich die
Nummern also — `/list` zeigt den aktuellen Stand.

`TELEGRAM_ENABLED=false` schaltet den Poller ab; API und Display laufen weiter.

## Web-Attrappe des Displays

```
http://localhost:8000/display?key=DEIN_API_KEY
```

Der Key wandert einmalig in den `localStorage`, danach genügt `/display`. Die
Seite bildet das M5Paper nach: feste 960×540, reines Schwarzweiß, große Schrift,
Tap-Ziele von 68 px. Ein Tipp auf eine Zeile hakt die Aufgabe ab.

Sie fragt dieselben Endpunkte ab wie später das Gerät — nur häufiger
(alle 10 Sekunden statt einmal pro Minute), damit man beim Entwickeln nicht
wartet.

## API

Alle `/api/*`-Routen brauchen den Header `X-API-Key`, sonst kommt 401.
Ohne gesetztes `API_KEY` antwortet die API grundsätzlich mit 401.

| Route | Beschreibung |
|---|---|
| `GET /api/tasks?done=false` | Liste; offene zuerst, neueste zuletzt |
| `POST /api/tasks` | Body `{"text": "..."}`, `source="api"` |
| `POST /api/tasks/{id}/done` | hakt ab, setzt `done_at`, idempotent |
| `POST /api/tasks/{id}/undone` | macht das Abhaken rückgängig |
| `DELETE /api/tasks/{id}` | löscht |
| `GET /api/display` | fertige Ansicht für das Gerät |
| `GET /api/display/version` | nur `{"version": "..."}` |
| `GET /healthz` | ohne Auth |

```bash
curl -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
     -d '{"text":"Rechnung Stadtwerke prüfen"}' \
     http://localhost:8000/api/tasks
```

### Display-Payload

```json
{
  "version": "a1b2c3d4",
  "generated_at": "2026-09-06T08:00:00Z",
  "open_count": 7,
  "items": [
    {"id": 42, "text": "Rechnung Stadtwerke prüfen", "age_days": 3}
  ]
}
```

Das Gerät muss nichts rechnen: Der Text ist serverseitig auf 38 Zeichen gekürzt
(mit `…`), die Liste auf `DISPLAY_LIMIT` Einträge begrenzt, `age_days` ist
fertig ausgerechnet. `open_count` zählt alle offenen Aufgaben, auch die
abgeschnittenen.

`version` ist ein 8 Zeichen kurzer SHA-256 über die IDs und Texte der
ausgelieferten Einträge — bewusst ohne Zeitstempel und ohne `age_days`, damit
er sich nicht von allein ändert. Gleiche Liste heißt gleiche Version, auch
Tage später.

## Umgebungsvariablen

| Variable | Default | Bedeutung |
|---|---|---|
| `API_KEY` | – | Schlüssel für alle `/api`-Routen. Leer = alles 401 |
| `TELEGRAM_TOKEN` | – | Token vom BotFather |
| `TELEGRAM_CHAT_ID` | `0` | eigene Chat-ID; `0` = Einrichtungsmodus |
| `TELEGRAM_ENABLED` | `true` | Poller an/aus |
| `DB_PATH` | `/data/tasks.db` | Pfad der SQLite-Datei |
| `DISPLAY_LIMIT` | `12` | maximale Einträge im Display-Payload |
| `KEEP_DONE_DAYS` | `30` | erledigte Aufgaben werden danach gelöscht |

Aufgeräumt wird beim Start und danach einmal täglich.

## Tests

```bash
.venv/bin/python -m pytest
```

Die Tests laufen gegen eine SQLite-Datei im Temp-Verzeichnis, ohne Netzwerk und
ohne Telegram-Poller. Die Telegram-Verarbeitung wird als reine Funktion
getestet.

## Was der ESP32-Client später tun muss

Auf dem Gerät liegt keine Logik, nur Zeichnen und zwei HTTP-Aufrufe:

1. **Version pollen** — einmal pro Minute
   `GET /api/display/version` mit `X-API-Key`. Antwort sind wenige Bytes.
2. **Nur bei Abweichung** von der zuletzt gezeichneten Version
   `GET /api/display` holen und das Panel neu zeichnen. Bleibt die Version
   gleich, wird nichts gezeichnet — das spart Strom und das für E-Ink typische
   Blinken.
3. **Rendern**: `items` der Reihe nach ausgeben, Text ist bereits gekürzt.
   `age_days` als kleiner Hinweis rechts, `open_count` in die Kopfzeile.
   Passen weniger Zeilen aufs Panel als geliefert, den Rest als
   „+ N weitere" anzeigen — so macht es auch die Web-Attrappe.
4. **Tap**: Berührung auf eine Zeile → `POST /api/tasks/{id}/done` mit
   `X-API-Key`, danach direkt `GET /api/display` und neu zeichnen. Bei einem
   Fehler den alten Stand stehen lassen und beim nächsten Poll korrigieren.

Der API-Key gehört in die Firmware-Konfiguration, nicht in den Code.
