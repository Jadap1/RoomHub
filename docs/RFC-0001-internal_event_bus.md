# RFC-001: Internal Event Bus

## Status

Accepted — implementation in progress.

## Objective

Introduce a typed internal event bus that decouples RoomHub components.

Network messages received from endpoints will be translated into internal events. Services and integrations will subscribe to those events without the original sender knowing which components handle them.

## Scope

RFC-001 covers:

* Typed internal events
* Event publication and subscription
* Entity command events
* Home Assistant command subscription
* Subscriber error isolation
* Duplicate-subscription prevention
* Tests for the existing light-toggle path

RFC-001 does not cover:

* The real Home Assistant WebSocket API
* Automatic Home Assistant entity discovery
* Persistent event history
* Distributed messaging
* Event replay
* Endpoint protocol changes

## Design principles

### Network messages and internal events are different

Endpoint network message:

```json
{
  "version": "1.0",
  "id": "message-id",
  "type": "input.button",
  "source": "kitchen-test-panel",
  "target": "roomhub-core",
  "payload": {
    "button": "lights"
  }
}
```

Internal event:

```python
EntityCommandEvent(
    entity_id="light.kitchen_main",
    command="toggle"
)
```

Network messages are untrusted transport data. Internal events are validated Python objects.

### Publishers do not know subscribers

A publisher emits an event but does not know whether it will be handled by:

* Home Assistant
* Logging
* Metrics
* Screen updates
* Notifications
* Automations

### Home Assistant owns physical entity state

RoomHub publishes commands to Home Assistant.

RoomHub updates its cached state only after receiving a Home Assistant state update.

The temporary simulated Home Assistant response used during RFC-001 will be removed by the real connector RFC.

### Events describe things that happened or were requested

Naming conventions:

* `EntityCommandEvent`: a request to perform an entity action
* `EntityStateChangedEvent`: a confirmed entity state update
* `EndpointConnectedEvent`: an endpoint established a connection
* `ScreenRequestedEvent`: a screen change was requested

Event class names use PascalCase and end with `Event`.

## Event delivery

RFC-001 uses in-process sequential delivery.

For each published event:

1. Find subscribers registered for its exact event class.
2. Call subscribers in registration order.
3. Await each subscriber.
4. Isolate subscriber failures so one subscriber cannot prevent later subscribers from running.
5. Report failures through logging.

Sequential delivery is intentional for the initial implementation because it is deterministic and easy to debug.

Parallel delivery may be considered later for independent, slow subscribers.

## Subscription lifecycle

Subscriptions are registered once during RoomHub startup.

The event bus must prevent the same handler from being subscribed to the same event class more than once.

This is particularly important when Uvicorn reload mode is used.

## Error handling

A subscriber exception must not crash the event bus or stop other subscribers.

The event bus records:

* Event class
* Subscriber name
* Exception details

Publishing returns an event-delivery result containing successful and failed subscriber counts.

## Event bus API

```python
event_bus.subscribe(
    EntityCommandEvent,
    handler
)

result = await event_bus.publish(event)
```

The publisher may inspect the result for diagnostics, but normal business logic must not depend on the number of subscribers.

## Initial vertical slice

RFC-001 migrates this path:

```text
Endpoint button
    ↓
input.button network message
    ↓
Input handler
    ↓
Command router
    ↓
Light handler
    ↓
EntityCommandEvent
    ↓
Event bus
    ↓
Home Assistant connector
```

The light handler must not import or call the Home Assistant connector directly.

## Acceptance criteria

RFC-001 is complete when:

1. RoomHub Core starts without import errors.
2. Event subscriptions are registered once.
3. The API light-toggle test publishes one `EntityCommandEvent`.
4. The endpoint simulator button publishes one `EntityCommandEvent`.
5. Home Assistant connector receives the event once.
6. A simulated Home Assistant state update changes the cached entity state.
7. A second toggle returns the state to its previous value.
8. An intentionally failing test subscriber does not stop another subscriber.
9. Existing registration, heartbeat, display and input functions continue working.
10. The working tree is committed with the RFC implementation.
