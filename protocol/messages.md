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