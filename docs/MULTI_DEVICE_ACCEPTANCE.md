# Multi-device acceptance

Use this checklist when adding the second physical Tab5. It verifies that a
new display can join without changing or interrupting an existing display.

## Provision the new display

1. Keep the existing endpoint online and note its endpoint ID, area, dashboard
   preferences, and firmware version.
2. Open the [RoomHub browser installer](https://jadap1.github.io/RoomHub/) in
   desktop Chrome or Edge and install the latest signed factory firmware.
3. In RoomHub, create a new single-use credential with the new display's name
   and area. Never reuse another display's credential or endpoint ID.
4. Use **Pair with RoomHub** in the installer to send the credential, reachable
   RoomHub LAN URL, and Wi-Fi details over USB.
5. Confirm both endpoints remain connected and have different endpoint IDs,
   even if they were given the same friendly name.

## Verify isolation

- Both Home Assistant devices expose their own connectivity, screen, volume,
  microphone, battery, and camera entities.
- Changing area or dashboard preferences affects only the selected display.
- Endpoint controls, notifications, camera requests, and OTA deployments affect
  only the selected endpoint.
- Intercom lists both endpoints and audio can be started in each direction.

## Persistence and recovery

1. Restart RoomHub and power-cycle both displays.
2. Confirm both reconnect with their original IDs, areas, and preferences.
3. Confirm Home Assistant has no duplicate devices or entities.
4. If needed, reinstall and re-pair only the new display; the existing display
   must remain unaffected.
