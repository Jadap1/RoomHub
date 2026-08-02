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

RoomHub endpoints connect through `WS /ws`.

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
