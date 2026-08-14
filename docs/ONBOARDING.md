# RoomHub device onboarding

This guide covers a new Home Assistant installation and additional Tab5
endpoints. The supported endpoint is currently the M5Stack Tab5.

## Before connecting a device

1. Add `https://github.com/Jadap1/RoomHub` as a Home Assistant add-on
   repository.
2. Install and start the **RoomHub** add-on.
3. In add-on configuration, set the Home Assistant public URL to an address
   reachable by the Tab5 and select the local Assist pipeline.
4. Expose RoomHub TCP port `8000` to the local network.
5. Install this repository through HACS as an **Integration**, restart Home
   Assistant, and add **RoomHub** from **Settings > Devices & services**.

The integration normally uses the Supervisor-internal URL
`http://cf9aeebe-roomhub:8000`. A physical endpoint must instead use the Home
Assistant host's LAN URL, such as `http://192.168.1.20:8000`.

The Assist pipeline must include the desired speech-to-text and text-to-speech
providers. Do not configure a Home Assistant wake-word stage: the endpoint
detects **Jarvis** locally and streams only post-wake command audio.

## First installation

An empty or factory Tab5 requires one USB bootstrap installation. Download the
factory image and `SHA256SUMS` from the same RoomHub release and verify its
checksum before continuing.

The preferred installation method is the RoomHub browser installer:

1. Open the installer in desktop Chrome or Edge using HTTPS.
2. Connect the Tab5 with a known USB data cable.
3. Select **Install signed firmware** and choose the Tab5 serial device.
4. Allow the installation to erase the endpoint configuration.
5. Open RoomHub's management page, choose **Pair a new display**, select its
   friendly name and area, and enter the add-on's firmware administration token.
6. Copy the generated single-use pairing credential. It expires after ten
   minutes and RoomHub stores only its SHA-256 hash.
7. Wait for the Tab5 to restart into provisioning mode.
8. Enter the friendly device name, pairing credential, RoomHub LAN URL, Wi-Fi
   network, and Wi-Fi password in the installer.
9. Select the Tab5 serial device again and submit the configuration.

Wi-Fi credentials travel directly from the browser to the Tab5 over Web Serial.
The installer does not send them to a website or place them in a URL.

Until the browser installer is published, developers can provision from an
activated ESP-IDF terminal:

```text
python firmware/endpoint/tools/provision_endpoint.py --port COM3
```

The helper prompts for all values and does not echo the Wi-Fi password.

## First registration

After provisioning, the endpoint restarts and:

1. connects through the Tab5 ESP32-C6 Wi-Fi coprocessor;
2. opens RoomHub's `/ws` endpoint;
3. registers its stable endpoint identity and capabilities;
4. appears in the RoomHub management page for name and area confirmation;
5. receives the dashboard for that area; and
6. appears as a Home Assistant device through the RoomHub integration.

Do not reuse an endpoint ID. The browser installer generates an opaque random
suffix so two endpoints given the same friendly name still have distinct
identities. RoomHub binds the single-use pairing credential to that ID on first
registration; later connections must present the same device credential.

## Additional devices

Repeat the factory installation and provisioning steps for each new Tab5. A
new endpoint does not disturb existing endpoint assignments or preferences.
Confirm the new endpoint's area in RoomHub after it first registers.

## Updates

The USB bootstrap installs a signed-apps-only bootloader and signed
application. RoomHub then distributes later signed application images over OTA.
The endpoint verifies size and SHA-256, installs into the inactive slot, and
confirms the update only after reconnecting to RoomHub. Failed health checks
roll back to the previous application.

Never install an OTA image signed by another key. Never distribute the signing
private key with a release.

## Recovery

Use these steps in order:

1. Leave the endpoint powered for at least one reconnect cycle; Wi-Fi and
   RoomHub retries back off to 30 seconds.
2. Power-cycle the endpoint and confirm both connection indicators.
3. Re-run USB provisioning if the Wi-Fi network or RoomHub LAN address changed.
4. If the application cannot boot, use the browser installer to reinstall the
   signed factory image. This erases endpoint configuration and requires pairing
   again.

The Tab5 has one physical button: a short press resets the board; holding it
while applying power enters the USB bootloader. There are not separate reset
and boot buttons.

## Release maintainer procedure

From a clean ESP-IDF 5.4.4 environment, build the endpoint and package a release:

```text
cd firmware/endpoint
./build.ps1
python tools/package_release.py --key D:/secure/roomhub-endpoint.pem --version 0.8.0 --download-base-url https://github.com/Jadap1/RoomHub/releases/download/endpoint-v0.8.0
```

The `dist` directory contains:

- a signed OTA application image;
- a complete merged 16 MB-layout factory image;
- an ESP Web Tools manifest;
- the exact ESP-IDF flash layout; and
- SHA-256 checksums.

Build artifacts are not source files and must be attached to the corresponding
release rather than committed.
