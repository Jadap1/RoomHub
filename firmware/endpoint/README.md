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

- ESP-IDF 5.4 or later
- Target: `esp32p4`
- ESP-SR 2.4.x
- Espressif M5Stack Tab5 BSP 1.2.x

After installing ESP-IDF:

```text
idf.py set-target esp32p4
idf.py build
```

The first hardware build must confirm the Tab5 microphone channel order before
the AFE capture adapter is enabled. The ES7210 supplies two microphones and the
board's ES8388/ES7210 audio path is owned by the Tab5 BSP.

## Layout

- `components/roomhub_voice`: portable voice-session state and privacy rules.
- `main`: endpoint composition and, later, board-profile selection.
- `components/roomhub_voice/test`: ESP-IDF Unity component tests for the
  portable state machine.

Network audio transport and the concrete Tab5 AFE adapter are deliberately the
next milestone: the state machine must remain testable without hardware.
