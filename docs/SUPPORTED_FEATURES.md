# Supported features

This is the RoomHub pre-1.0 support baseline for the M5Stack Tab5 endpoint.

| Capability | Support |
| --- | --- |
| Local Jarvis wake word and Home Assistant Assist | Supported |
| Piper speech playback and spoken notifications | Supported |
| Lights, switches, climate, fans, covers, scenes, and scripts | Supported |
| Media players, locks, buttons, booleans, numbers, and selects | Supported |
| Grouped or direct dashboards with per-endpoint preferences | Supported |
| Screen sleep/wake, volume, microphone privacy, and battery status | Supported |
| Home Assistant camera snapshots | Supported |
| Priority, queued, actionable, visual, and spoken notifications | Supported |
| Endpoint intercom and PC test receiver | Supported |
| Signed USB installation, signed OTA, health confirmation, rollback | Supported |
| Multiple endpoint identities and isolated configuration | Software verified; physical acceptance pending |
| Continuous camera streaming | Planned enhancement after 1.0 |
| Non-Tab5 and Android endpoints | Planned platform expansion after enhancements |

RoomHub is local-first. The add-on API and endpoint WebSocket are intended for
a trusted home network. Use an HTTPS/WSS reverse proxy or an isolated device
network where untrusted clients can access the LAN.
