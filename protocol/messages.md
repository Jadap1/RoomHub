# RoomHub Messages

## Endpoint Messages

Messages related to device registration and status.

---

# endpoint.challenge

Direction: Core to Endpoint

Purpose:

Supplies a fresh registration nonce immediately after the WebSocket opens.
Authenticated endpoints calculate `device_proof` as lowercase hexadecimal
HMAC-SHA256 over `nonce + ":" + device_id`. The HMAC key is the SHA-256 digest
of the USB-provisioned pairing credential. The credential itself is never sent
over Wi-Fi.

```json
{
  "version": "1.0",
  "type": "endpoint.challenge",
  "payload": {"nonce": "fresh-unpredictable-value"}
}
```

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
    "device_proof": "64-lowercase-hexadecimal-characters",
    "capabilities": [
      "display",
      "speaker",
      "microphone"
    ]
  }
}
```

RoomHub rejects unassigned endpoints without a valid proof. A valid unused
pairing credential is consumed and bound to the submitted device ID. Subsequent
connections must answer each fresh challenge using that same credential.

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
the transcript in its payload. When Piper synthesis succeeds, the payload also
contains a `speech` object with an audio `url` and `mime_type`. Failure to create
speech does not change the intent result; `speech_status` is then `unavailable`.
The audio URL is absolute so endpoints do not need Home Assistant connection
details or credentials.

---

# voice.audio.cancel

Direction:

Endpoint to Core

Purpose:

Aborts the current audio session without resolving an intent. Core responds
with `voice.audio.cancelled`.

# Room-to-room intercom

Intercom calls use a server-issued `call_id` and have two phases: `ringing` and
`active`. Both endpoints must advertise `microphone` and `speaker` capabilities.
An endpoint can participate in only one call at a time.

The caller sends `intercom.start` with `target_endpoint_id`, `sample_rate`
(`16000`), `channels` (`1`), and `format` (`pcm_s16le`). Core reserves both
endpoints, sends `intercom.incoming` to the receiver, and replies with
`intercom.ringing` to the caller. Both messages include the same `call_id`.

The receiver answers with `intercom.status` containing that `call_id` and a
`status` of `accepted` or `declined`. Acceptance produces `intercom.active` at
both endpoints. The call rings for at most 30 seconds; unanswered calls end
with reason `no_answer` for the caller and `missed` for the receiver.

During an active call either participant may send binary WebSocket frames of
raw mono 16-bit little-endian PCM. Core routes each frame to the other
participant. The endpoint UI currently provides half-duplex hold-to-talk so
only the participant holding its talk control transmits.

Either participant ends the call with `intercom.end` (or aborts it with
`intercom.cancel`), including the `call_id`. Core sends `intercom.ended` to
both participants. Disconnecting either endpoint also releases the call.

Example call request:

```json
{
  "version": "1.0",
  "type": "intercom.start",
  "source": "tab5-01",
  "target": "roomhub-core",
  "payload": {
    "target_endpoint_id": "tab5-02",
    "sample_rate": 16000,
    "channels": 1,
    "format": "pcm_s16le"
  }
}
```

---

# audio.play

Direction: Core to Endpoint

Queues an MP3 with the endpoint's single audio owner. `priority` is one of
`emergency`, `intercom`, `voice_assistant`, `media`, or `notification`.
Higher-priority requests interrupt lower-priority playback; equal and lower
priorities are queued in priority order.

```json
{
  "version": "1.0",
  "type": "audio.play",
  "source": "roomhub-core",
  "target": "kitchen-panel",
  "payload": {
    "request_id": "doorbell-202",
    "url": "https://roomhub.local/audio/doorbell.mp3",
    "mime_type": "audio/mpeg",
    "priority": "notification"
  }
}
```

---

# audio.stop

Direction: Core to Endpoint

Cancels the active or queued request matching `request_id`.

---

# audio.status

Direction: Endpoint to Core

Reports `accepted`, `rejected`, `playing`, `completed`, `interrupted`,
`failed`, `stopped`, or `not_found` for an audio request. Core responds with
`audio.status.ack` so delivery is visible on both sides of the connection.

---

# audio.play

Direction: Core to Endpoint

Queues an MP3 with the endpoint's single audio owner. `priority` is one of
`emergency`, `intercom`, `voice_assistant`, `media`, or `notification`.
Higher-priority requests interrupt lower-priority playback; equal and lower
priorities are queued in priority order.

```json
{
  "version": "1.0",
  "type": "audio.play",
  "source": "roomhub-core",
  "target": "kitchen-panel",
  "payload": {
    "request_id": "doorbell-202",
    "url": "https://roomhub.local/audio/doorbell.mp3",
    "mime_type": "audio/mpeg",
    "priority": "notification"
  }
}
```

---

# audio.stop

Direction: Core to Endpoint

Cancels the active or queued request matching `request_id`.

---

# audio.status

Direction: Endpoint to Core

Reports `accepted`, `rejected`, `playing`, `completed`, `interrupted`,
`failed`, `stopped`, or `not_found` for an audio request. Core responds with
`audio.status.ack` so delivery is visible on both sides of the connection.
# Endpoint controls

RoomHub sends `endpoint.control` to a connected endpoint with a unique
`request_id` and one or both of `screen_on` (boolean) and `volume` (integer
0–100). The endpoint applies only these bounded controls and responds with
`endpoint.control.status`, including the request ID, `applied` or `rejected`,
and its resulting screen and volume state. Heartbeats repeat this state under
`payload.controls` so controllers do not rely on optimistic updates.
