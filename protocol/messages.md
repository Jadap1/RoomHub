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
