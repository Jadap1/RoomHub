# RoomHub Technical Principles

## Hardware Independence

RoomHub must not depend on a single hardware platform.

Hardware provides capabilities.

The platform provides intelligence.

---

## Separation of Concerns

Each component should have a clear responsibility.

Endpoints:

- Interface
- Sensors
- Audio
- Display

Server:

- Intelligence
- Coordination
- Context
- Services

---

## Local First

Core functionality should operate without cloud dependency.

Cloud services may be optional integrations.

---

## Event Driven

Components communicate through events rather than direct dependencies.

This allows services to evolve independently.

---

## Room Centric Design

The room is the primary interaction model.

Hardware is assigned to rooms.

---

## Capability Based Design

Features depend on capabilities rather than device models.

Example:

A device with a speaker can receive audio.

The platform does not care whether it is a Tab5 or ESP32-P4.

---

## Versioned Interfaces

All communication protocols must be versioned.

Future devices must remain compatible.

---

## Avoid Premature Hardware Optimisation

The first goal is a stable platform.

Hardware-specific optimisation should happen after the architecture is proven.

---

## Quality Over Speed

RoomHub should be designed as a long-term platform.

Clean architecture is preferred over quick prototypes.