# RoomHub

RoomHub is a local-first room intelligence platform for Home Assistant and
room-based endpoints such as ESP32-P4 panels.

The current server connects to Home Assistant over its WebSocket API and
provides:

- live entity discovery and state synchronization;
- floor, area, device, and entity registry synchronization;
- live registry update handling;
- Home Assistant service calls for entity commands;
- SQLite caching and restart recovery;
- HTTP and WebSocket interfaces for RoomHub endpoints.

## Server setup

RoomHub Core currently targets Python 3.12 or later.

From `roomhub/server`, create a virtual environment and install the pinned
dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Copy `config/homeassistant.example.json` to
`config/homeassistant.json`, then set the Home Assistant URL and a long-lived
access token. The real configuration file is ignored by Git.

Start the server with:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

RoomHub creates and migrates `roomhub.db` automatically. The database and its
WAL/SHM sidecars are runtime files and are not tracked by Git.

## API

The current read-only discovery endpoints are:

- `GET /health`
- `GET /entities`
- `GET /entities/{entity_id}`
- `GET /floors`
- `GET /floors/{floor_id}`
- `GET /areas`
- `GET /areas/{area_id}`
- `GET /devices`
- `GET /devices/{device_id}`
- `PUT /endpoints/{endpoint_id}/area/{area_id}`
- `PUT /firmware/endpoint` with `X-RoomHub-Admin-Token`,
  `X-Firmware-Version`, and a raw ESP image body
- `GET /firmware/endpoint/manifest`
- `POST /firmware/endpoint/deploy/{endpoint_id}` with
  `X-RoomHub-Admin-Token`
- `POST /notifications`
- `GET /notifications/{delivery_id}`

RoomHub endpoints connect through `WS /ws`.

## Room notifications

Assign a connected endpoint to one of the Home Assistant area IDs returned by
`GET /areas`:

```text
PUT /endpoints/tab5-01/area/kitchen
```

Then synthesize and deliver a Piper notification to every connected speaker in
that area:

```json
POST /notifications
{
  "text": "Someone is at the front door",
  "area_id": "kitchen",
  "priority": "notification"
}
```

Use `endpoint_id` instead of `area_id` to target one endpoint. The returned
`delivery_id` can be read from `GET /notifications/{delivery_id}`; RoomHub
tracks each endpoint through accepted, playing, and terminal playback states.

Home Assistant can call the same API from an automation with a `rest_command`:

```yaml
rest_command:
  roomhub_notify:
    url: "http://cf9aeebe-roomhub:8000/notifications"
    method: POST
    content_type: application/json
    payload: >-
      {"text": {{ text | tojson }}, "area_id": {{ area_id | tojson }},
      "title": {{ title | default('RoomHub') | tojson }},
      "priority": {{ priority | default('notification') | tojson }},
      "display": {{ display | default(true) | tojson }},
      "speak": {{ speak | default(true) | tojson }}}
```

Set `display: false` for speech-only announcements or `speak: false` for a
silent visual alert. At least one channel must remain enabled. The RoomHub
management page also includes a composer with live area and endpoint selectors.

## Tests

Run the dependency-free regression suite from `roomhub/server`:

```powershell
.\.venv\Scripts\python.exe -W error::DeprecationWarning -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app tests
```

The suite uses temporary databases and a fake Home Assistant connector. Live
Home Assistant checks are intentionally separate because they require local
credentials and network access.

GitHub Actions runs the same tests and compilation checks for server-related
pushes and pull requests.

## Home Assistant app mode

When `ROOMHUB_RUNTIME_MODE=homeassistant_app` and `SUPERVISOR_TOKEN` are
available, RoomHub connects through the Supervisor WebSocket endpoint and
loads application options from `/data/options.json` by default. Set
`ROOMHUB_OPTIONS_PATH` to override that options path.

## Project documentation

The design goals and architecture are documented under [`docs`](docs/).

## Endpoint firmware

The portable ESP32-P4 endpoint firmware starts under
[`firmware/endpoint`](firmware/endpoint/). Its first board profile is the
M5Stack Tab5, but wake-word and voice-session behaviour is kept independent
from the board support package.
## Home Assistant installation

This repository is a Home Assistant app repository. In Home Assistant, open
**Settings > Apps > App store**, add this repository URL, then install RoomHub:

```text
https://github.com/Jadap1/RoomHub
```

Set the Home Assistant public URL to a LAN address that endpoints can reach,
then start the app. RoomHub publishes its endpoint service on TCP port `8000`.
The app receives a scoped Supervisor token automatically; no long-lived Home
Assistant access token is required.
