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
