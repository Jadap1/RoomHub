# RoomHub ESP32-P4 endpoint

This ESP-IDF project hosts RoomHub's portable endpoint firmware. The initial
hardware profile is the M5Stack Tab5; later ESP32-P4 boards should implement
the same board interfaces without changing voice-session behaviour.

## Privacy boundary

The microphone feeds the on-device ESP-SR audio front end continuously for
wake-word detection. Audio is not eligible for network transport while the
session is in `waiting_for_wake_word`. Only processed command audio received
after WakeNet detects **Jarvis** can be streamed. Streaming ends on local VAD
end-of-speech, capture timeout, cancellation, or transport failure.

The selected bundled model is `wn9_jarvis_tts`. Do not enable a Home Assistant
wake-word stage for this endpoint; Home Assistant should run the RoomHub Local
pipeline from STT to STT and from TTS to TTS as separate operations.

## Toolchain

- ESP-IDF 5.4.4 (verified build version)
- Target: `esp32p4`
- ESP-SR 2.4.x
- Espressif M5Stack Tab5 BSP 1.2.x
- ESP-Hosted 1.4.0 and ESP Wi-Fi Remote 0.8.5

The hosted Wi-Fi versions are intentionally pinned to the versions used with
M5Stack's factory ESP32-C6 Wi-Fi SDIO firmware. Do not upgrade either side in
isolation; the P4 host and C6 coprocessor firmware must remain compatible.

After installing and activating ESP-IDF, select the target once:

```text
idf.py set-target esp32p4
```

On Windows, build with:

```text
.\build.ps1
```

The wrapper enables UTF-8 for ESP-SR's model packaging output before invoking
the standard `idf.py build` command.

On other platforms, build with `idf.py build` directly.

The first hardware prototype uses the Tab5 BSP's verified 16 kHz, 16-bit mono
capture path. That stream feeds a one-microphone ESP-SR AFE pipeline containing
VADNet and `wn9_jarvis_tts`. The ES7210 enables both physical microphones, but
multi-microphone enhancement is deferred until it provides a measurable benefit.

On the M5Stack Tab5 board revision 2, hardware testing has confirmed model
loading, continuous microphone capture, and successful spoken **Jarvis**
detection. The landscape status screen reports whether the detector is starting,
listening, or has detected the wake word.

The onboard ESP32-C6 is powered through the Tab5 I/O expander and connected to
the ESP32-P4 over four-bit SDIO. Hardware testing has confirmed the hosted link
and a credential-free nearby-network scan. A provisioned endpoint uses the same
transport to connect to its stored Wi-Fi network and waits for a network address
before starting continuous Jarvis tasks. SSIDs and credentials are never logged,
and audio remains local throughout wireless setup.

After Wi-Fi is available, the endpoint opens the RoomHub `/ws` control service,
registers its stable endpoint ID and hardware capabilities, and sends a status
heartbeat every ten seconds. Wi-Fi and RoomHub recovery use bounded exponential
backoff from one to thirty seconds. WebSocket ping/pong checks detect half-open
connections after an access-point outage; every terminal connection failure
tears down and restarts the client before registering the endpoint again. The
status screen distinguishes connecting, registered, and retrying states. During
every interruption, command audio remains ineligible for network transport and
local wake-word privacy remains active.

## Persistent configuration

Endpoint identity, the RoomHub server URL, and Wi-Fi credentials are stored in
the ESP-IDF NVS partition. They are never compiled into the firmware or logged.
The firmware validates all values on load and remains in an unprovisioned state
until every required value has been stored. An unprovisioned endpoint waits for
one-time setup over its USB Serial/JTAG connection before starting wireless or
wake-word tasks. With the board connected, run this from an ESP-IDF terminal:

```text
python tools/provision_endpoint.py --port COM3
```

The helper prompts locally for the endpoint ID, RoomHub URL, Wi-Fi network name,
and Wi-Fi password. The password is hidden, is not accepted as a command-line
argument, and neither the helper nor firmware echoes any supplied value. Valid
settings are saved through `roomhub::config::EndpointConfigStore`, then the
endpoint restarts and follows its normal provisioned startup path.

The prototype does not yet enable NVS encryption. Flash encryption and secure
boot should be enabled together after the first hardware bring-up, because
their production settings affect flashing and recovery.

## Firmware signing

OTA images use ESP-IDF Secure Boot v2 RSA signatures in signed-apps-only mode.
This rejects untrusted network updates without burning eFuses or disabling USB
recovery. Keep the RSA-3072 private key outside the repository and back it up
offline. Build normally, then sign the padded application image from an
activated ESP-IDF terminal:

```text
.\tools\sign_endpoint_firmware.ps1 -KeyPath D:\secure\roomhub-endpoint.pem -OutputPath build\roomhub_endpoint-signed.bin
```

The first signed-apps-only bootloader and signed application require one USB
bootstrap flash. Subsequent OTA images must use the same key. Hardware Secure
Boot and flash-encryption eFuses remain disabled until a separate production
lock-down procedure is explicitly approved.

## Flash layout

The 16 MB flash contains two 4 MB application slots plus OTA selection data,
so RoomHub can install and verify a new firmware image without overwriting the
running image. The endpoint checks the advertised size and SHA-256 digest before
selecting the inactive slot, then confirms the new image only after it reconnects
and registers with RoomHub. If that health check is not reached, the rollback-
enabled bootloader preserves the previous working image. The remaining space
provides 3 MB for ESP-SR
models, about 4.9 MB for future assets, and NVS for device configuration. With
an erased OTA selection partition, ESP-IDF boots `ota_0` on the initial flash.

## Layout

- `components/roomhub_config`: validated, persistent endpoint configuration.
- `components/roomhub_firmware`: portable semantic-version upgrade policy.
- `components/roomhub_recovery`: portable bounded reconnect-backoff policy.
- `components/roomhub_voice`: portable voice-session state and privacy rules.
- `main`: endpoint composition and, later, board-profile selection.
- `components/roomhub_voice/test`: ESP-IDF Unity component tests for the
  portable state machine.

The concrete Tab5 AFE adapter keeps all pre-wake audio local. After Jarvis is
detected, the endpoint streams only the command capture to RoomHub, waits for
the resolved intent, downloads Piper's returned MP3 over HTTP(S), decodes it
incrementally, and renders the PCM response as 16 kHz mono to match the Tab5's
shared microphone/speaker I2S clock. The amplifier is enabled only for playback,
microphone feeding is paused during it, and the AFE buffer is reset afterward
so the spoken response cannot become a stale wake-word input. The portable
session state machine remains independently testable without hardware.

All speaker output now passes through the central endpoint audio service.
Emergency, intercom, voice-assistant, media, and notification requests have
explicit priorities; higher priorities interrupt lower ones and other requests
queue in priority order. A wake word cancels lower-priority playback before
command capture so notification audio cannot be sent to speech recognition.
