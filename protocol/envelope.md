# RoomHub Message Envelope

## Purpose

All communication between RoomHub Core and endpoints uses a standard message envelope.

The envelope provides:

- Versioning
- Identification
- Routing
- Debugging information
- Future compatibility

## Structure

Every message contains:

| Field | Description |
|---|---|
| version | Protocol version |
| message_id | Unique message identifier |
| timestamp | Message creation time |
| type | Message purpose |
| source | Sending component |
| target | Receiving component |
| payload | Message-specific data |

## Example

```json
{
  "version": "1.0",
  "message_id": "a12345",
  "timestamp": "2026-08-01T12:00:00Z",
  "type": "display.show",
  "source": "roomhub-core",
  "target": "kitchen-panel",
  "payload": {
    "screen": "home"
  }
}