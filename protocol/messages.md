# RoomHub Messages

## Endpoint Messages

Messages related to device registration and status.

---

# endpoint.register

Direction:

Endpoint → Core

Purpose:

Registers an endpoint with RoomHub Core.

Example:

```json
{
  "type": "endpoint.register",
  "payload": {
    "device_id": "kitchen-panel",
    "device_name": "Kitchen Panel",
    "room": "Kitchen",
    "capabilities": [
      "display",
      "speaker",
      "microphone"
    ]
  }
}
```

---

# voice.transcript

Direction:

Endpoint → Core

Purpose:

Submits speech-to-text output for safe intent resolution. `area_id` is
optional; when omitted, Core may infer it from the registered endpoint room.

Example:

```json
{
  "version": "1.0",
  "type": "voice.transcript",
  "source": "kitchen-panel",
  "target": "roomhub-core",
  "payload": {
    "text": "turn on the ceiling light",
    "area_id": "kitchen"
  }
}
```

Core responds with one of:

- `voice.intent.accepted` after the structured command was delivered.
- `voice.intent.rejected` when the transcript is invalid, unsupported,
  unknown, or ambiguous.
- `voice.intent.failed` when a resolved command could not be delivered.

The initial command vocabulary is deliberately narrow: turn on, turn off,
and toggle for lights, switches, fans, and input booleans. Ambiguous entity
names are never guessed.

---

# voice.audio.start

Direction:

Endpoint to Core

Purpose:

Starts one speech-to-text session after the endpoint has detected its local
wake word. The endpoint must already be registered. RoomHub accepts only one
active audio session per WebSocket connection.

```json
{
  "version": "1.0",
  "type": "voice.audio.start",
  "source": "kitchen-panel",
  "target": "roomhub-core",
  "payload": {
    "sample_rate": 16000,
    "channels": 1,
    "format": "pcm_s16le"
  }
}
```

Core responds with `voice.audio.ready`. Only then may the endpoint send binary
WebSocket frames containing raw PCM samples. Binary audio sent before a session
is ready is rejected, so ambient audio is never forwarded without an explicit
post-wake start message.

---

# voice.audio.end

Direction:

Endpoint to Core

Purpose:

Ends audio input after local silence detection. Core transcribes the utterance
with the configured Home Assistant Assist pipeline and passes the transcript to
RoomHub's safe intent resolver. The resulting `voice.intent.*` response includes
the transcript in its payload.

---

# voice.audio.cancel

Direction:

Endpoint to Core

Purpose:

Aborts the current audio session without resolving an intent. Core responds
with `voice.audio.cancelled`.
