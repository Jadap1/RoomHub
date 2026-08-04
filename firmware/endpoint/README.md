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

## Persistent configuration

Endpoint identity, the RoomHub server URL, and Wi-Fi credentials are stored in
the ESP-IDF NVS partition. They are never compiled into the firmware or logged.
The firmware validates all values on load and remains in an unprovisioned state
until every required value has been stored. The eventual USB provisioning flow
will use `roomhub::config::EndpointConfigStore`; it is intentionally deferred
until the physical board is available.

The prototype does not yet enable NVS encryption. Flash encryption and secure
boot should be enabled together after the first hardware bring-up, because
their production settings affect flashing and recovery.

## Flash layout

The 16 MB flash contains two 4 MB application slots plus OTA selection data,
so a future updater can install and verify a new firmware image without
overwriting the running image. The remaining space provides 3 MB for ESP-SR
models, about 4.9 MB for future assets, and NVS for device configuration. With
an erased OTA selection partition, ESP-IDF boots `ota_0` on the initial flash.

## Layout

- `components/roomhub_config`: validated, persistent endpoint configuration.
- `components/roomhub_voice`: portable voice-session state and privacy rules.
- `main`: endpoint composition and, later, board-profile selection.
- `components/roomhub_voice/test`: ESP-IDF Unity component tests for the
  portable state machine.

The concrete Tab5 AFE adapter is implemented and keeps all pre-wake audio local.
Network audio transport is deliberately the next milestone, and the portable
state machine remains independently testable without hardware.
