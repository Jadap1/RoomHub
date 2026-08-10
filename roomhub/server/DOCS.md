# RoomHub

RoomHub connects local ESP32-P4 endpoints to Home Assistant and its Assist
pipeline. The service publishes port `8000` for endpoint WebSocket and audio
traffic; keep this port on the trusted local network.

## Configuration

- **Assist pipeline name** must match the Home Assistant pipeline configured
  for RoomHub speech-to-text and text-to-speech.
- **Home Assistant public URL** must be reachable by RoomHub endpoints. Prefer
  the Home Assistant device's local IP address, for example
  `http://192.168.1.50:8123`, rather than `localhost` or an ingress URL.

The app uses Home Assistant's Supervisor-issued token internally. No long-lived
access token needs to be copied into its configuration.

RoomHub stores its runtime database in the app's persistent `/data` directory.

## Endpoint management

Open **RoomHub** from the Home Assistant sidebar, or select **Open Web UI** on
the app page. Each registered endpoint has an area selector and visibility
switches for the lights, switches, climate devices, fans, covers, scenes, and
scripts in that area. Saving updates the endpoint immediately. Visibility
choices persist across endpoint reconnects, app restarts, and temporary
assignment to another area.
Entities can also be reordered and marked as favourites. Favourites appear
first and receive a distinct highlight on compatible endpoint firmware.

Compatible endpoints can toggle lights and switches, adjust light brightness,
set climate temperature and mode, control fan power and percentage, open, stop,
and close covers, and activate scenes or scripts. Every command is checked
against the endpoint's assigned area before it is sent to Home Assistant.

Update, sensor, button, diagnostic, and configuration entities are excluded
from endpoint dashboards automatically.

## Home Assistant notification action

The app publishes `POST /notifications` on port `8000`. Home Assistant
automations can invoke it with a `rest_command` using `text` plus exactly one of
`area_id` or `endpoint_id`. RoomHub asks the configured Assist pipeline to
synthesize Piper speech, routes it only to connected endpoints with the
`speaker` capability, and records per-endpoint delivery state. Assign endpoint
areas with `PUT /endpoints/{endpoint_id}/area/{area_id}`; assignments persist in
the RoomHub database and are restored when endpoints reconnect.
