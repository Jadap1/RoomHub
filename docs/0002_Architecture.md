# RoomHub Architecture

## Overview

RoomHub follows a distributed architecture.

A central RoomHub Core server provides intelligence, coordination, and services.

Room endpoints provide the physical interaction layer.
             RoomHub Core
          (Central Server)

                |
 ---------------------------------

 |               |               |

Great. I think we have enough alignment now to move from vision into architecture.

I'm going to treat this as the beginning of the actual RoomHub design process. Before we write firmware, we need to define the boundaries between components.

RoomHub — Architecture v0.1
1. Core concept

A RoomHub installation consists of:

                    ┌──────────────────────┐
                    │     RoomHub Core     │
                    │   (Home Server)      │
                    │                      │
                    │ - Room intelligence  │
                    │ - AI orchestration   │
                    │ - Audio routing      │
                    │ - Device registry    │
                    │ - HA integration     │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼

        Kitchen Hub       Office Hub       Bedroom Hub

        Display          Display          Display
        Touch            Touch            Touch
        Mic              Mic              Mic
        Speaker          Speaker          Speaker
        Sensors          Sensors          Sensors

The RoomHub Core is the intelligence.

The room endpoints are the senses and interfaces.

2. RoomHub Core

This should run as a service on your home server.

Given your existing setup, this would likely be a Docker container or VM/LXC on Proxmox.

It contains several internal services.

Room Manager

The heart of the platform.

Maintains:

Rooms:
  Kitchen
  Living Room
  Office
  Bedroom

Endpoints:
  Kitchen Tablet
  Office Panel

People:
  Jamie
  Family

Capabilities:
  Display
  Audio
  Camera
Event Bus

Everything communicates through events.

Example:

Event:
person.entered_room

Payload:
{
 room:"Kitchen",
 person:"Jamie",
 time:"08:15"
}

or:

Event:
notification.created

Payload:
{
 priority:"high",
 target:"upstairs",
 message:"Garage door open"
}

This avoids services becoming tightly coupled.

Voice Service

Responsible for:

Wake word
Audio sessions
Speech-to-text
LLM requests
Text-to-speech

Important:

The LLM does not directly control devices.

It creates intents.

Example:

User:

"Make the kitchen warmer"

LLM:

intent:
 climate.set_temperature

room:
 kitchen

temperature:
 21

RoomHub decides how to execute that.

Audio Service

This is going to be one of our most important pieces.

It manages:

voice conversations
intercom calls
announcements
music playback
priority

Example priority:

Emergency announcement
        |
Intercom call
        |
Voice assistant
        |
Music
        |
Notifications

A fire alarm should interrupt music.

A phone call should interrupt a dashboard animation.

3. Endpoint design

The Tab5 is our first endpoint.

The firmware should have:

Core layer

Always present:

Connectivity
Authentication
OTA
Time synchronisation
Logging
Device health
Capability modules

Loaded depending on hardware:

Display Module

Audio Module

Touch Module

Camera Module

Sensor Module

Media Module

A future cheap wall switch could have:

Touch
LED
Temperature

A premium panel:

Display
Camera
Mic
Speaker
Presence

Same platform.

4. Communication protocol

I think we should define this before firmware.

The endpoint should announce:

Hello RoomHub.

I am:

Device:
M5Stack Tab5

Firmware:
0.1.0

Capabilities:

display
touch
microphone
speaker
camera

The server responds:

Welcome.

Assigned room:

Kitchen

Configuration:

Dashboard:
Kitchen_Default

Voice:
Enabled

Intercom:
Enabled
5. Initial technology decisions

My recommendations:

Endpoint
ESP-IDF
C++
LVGL
FreeRTOS
WebSockets initially
Server
Python
FastAPI
AsyncIO
PostgreSQL/SQLite initially
Docker deployment
Messaging

Start with:

WebSockets

Later possibly:

MQTT bridge

or

gRPC

6. First development milestone

Before touching the Tab5:

RoomHub Core Alpha

A server that can:

✅ Start
✅ Accept endpoint connections
✅ Register devices
✅ Display connected endpoints
✅ Send test commands
✅ Receive events

Example:

Server UI:

Connected Rooms

Kitchen
  M5Stack Tab5
  Online
  Display ✓
  Audio ✓


Then:

Press button:

Send notification

Tab5 displays:

Hello from RoomHub

That proves our foundation.

What I need you to do next

Before we write code, I need three decisions from you.

1. Where should RoomHub Core run initially?

Given your setup, my recommendation:

Docker container on your existing Proxmox server

Options:

Docker VM
Docker LXC
Home Assistant add-on later

I would not make it a Home Assistant add-on initially.

2. Repository location

Create:

RoomHub

on GitHub (private is fine).

Initial structure:

RoomHub/
├── docs/
├── server/
├── firmware/
├── protocol/
└── tools/
3. Development machine

What will you use for coding?

I assume:

VS Code
Windows desktop

but confirm.

Once those are confirmed, I suggest our next task is to write:

docs/0001_Project_Vision.md

and

docs/0002_Architecture.md

Then we create the repository and start building RoomHub Core before the Tab5 arrives.

This is now at the stage where we're no longer discussing an idea—we're designing a system.

What do you need me to do, please provide steps for any tasks that require my action

Perfect. From this point forward I'll separate "decisions/design" from "actions you need to take". I’ll avoid asking you to do anything unless it is genuinely required.

For the next stage, I need you to prepare the development environment and repository. No hardware work is needed yet.

Phase 0 — Project Setup
Task 1 — Create the RoomHub GitHub repository
Your action
Go to GitHub.
Create a new repository.

Use:

Repository name

RoomHub

Settings:

Visibility: Private (recommended initially)
Initialise with:
✅ README file
❌ .gitignore (we'll add our own)
❌ Licence (decide later)

When created, you should have:

RoomHub/
 └── README.md
Task 2 — Install development tools

You may already have some of these.

Please confirm after checking.

Required:
Git

Install:
https://git-scm.com/downloads

Verify:

Open PowerShell:

git --version

Expected:

git version 2.x.x
Visual Studio Code

You likely already have this.

Required extensions:

Install:

Python (Microsoft)
Pylance (Microsoft)
C/C++ (Microsoft)
PlatformIO IDE

In VS Code:

Extensions → Search → Install
Python

Install Python 3.12.

Check:

python --version

Expected:

Python 3.12.x
Task 3 — Install Docker

Because RoomHub Core will initially run as a container.

Install:

Docker Desktop

https://www.docker.com/products/docker-desktop/

During installation:

Enable:

✅ WSL2 backend

After installation:

docker --version

Expected:

Docker version xx.xx.xx
Task 4 — Clone the repository locally

After creating the GitHub repository:

Open PowerShell.

Choose a development folder.

Example:

cd C:\Projects

Clone:

git clone https://github.com/YOUR_USERNAME/RoomHub.git

Enter:

cd RoomHub
Task 5 — Create the initial folder structure

Create:

RoomHub
│
├── docs
│
├── server
│
├── firmware
│
├── protocol
│
├── simulator
│
└── tools

You can do this either:

Option A — VS Code

Right click → New Folder

or:

Option B — PowerShell

From inside RoomHub:

mkdir docs,server,firmware,protocol,simulator,tools
Task 6 — First commit

In PowerShell:

git add .

Then:

git commit -m "Initial RoomHub project structure"

Then:

git push
What I will do after you complete those tasks

Once you confirm:

"Repository created and tools installed"

I will provide the first project files:

docs/
 ├── 0001_Project_Vision.md
 ├── 0002_Architecture.md
 └── 0003_Technical_Principles.md

Then we will create:

server/

with the first RoomHub Core prototype:

Python project
Docker configuration
WebSocket server
Endpoint registration
Basic API

Before touching the Tab5.

One note based on your existing setup

Because you already run Proxmox and Home Assistant, I would eventually deploy RoomHub Core as a dedicated container alongside your existing services, something like:

Proxmox
│
├── Home Assistant OS
│
├── OpenMediaVault
│
├── RoomHub Core
│
├── Ollama
│
├── Whisper
│
└── Other services

But we won't do that yet. First we make the software portable and testable.

Your first action list is therefore:

✅ Create GitHub repo RoomHub
✅ Install/check Git
✅ Install/check VS Code extensions
✅ Install/check Python 3.12
✅ Install Docker Desktop
✅ Create folder structure
✅ Push initial commit

When that's done, tell me and we'll begin writing the actual RoomHub code.

Repository created and tools installed

Excellent. We now have the foundation in place.

Before we write any executable code, we are going to create the contract that the code must follow. This is the point where good projects either become maintainable or slowly turn into a collection of patches.

Our first commit will be documentation only.

Your next task: add the initial RoomHub documentation

Inside your repository, create these three files:

RoomHub/
│
├── docs/
│   ├── 0001_Project_Vision.md
│   ├── 0002_Architecture.md
│   └── 0003_Technical_Principles.md

I will provide the content for each file.

File 1
docs/0001_Project_Vision.md

Copy this:

# RoomHub Project Vision

## Overview

RoomHub is a local-first intelligent room platform designed to transform every room in a home into a unified smart endpoint.

Rather than requiring multiple independent devices for lighting control, voice assistants, dashboards, intercoms, notifications, and media control, RoomHub provides a single room-focused interface connected to a central home intelligence server.

The goal is to create a system where every room becomes a natural extension of the home's automation and intelligence.

---

## Vision Statement

RoomHub exists to make every room in a home an intelligent, local-first endpoint that naturally connects people with their home through voice, touch, audio, and contextual information.

By combining these capabilities into a single platform, RoomHub replaces isolated smart devices with a unified room experience powered by one central server.

---

## Core Philosophy

### The Room Is The Primary Concept

Traditional smart home systems are usually device-centric.

Examples:

- A light switch controls lights.
- A speaker plays music.
- A tablet displays dashboards.
- A voice assistant handles commands.

RoomHub is room-centric.

A room contains:

- People
- Devices
- Sensors
- Media
- Information
- Conversations
- Automation context

The room becomes the primary interaction point.

---

## Design Goals

RoomHub should:

- Be local-first
- Protect user privacy
- Avoid dependence on cloud services
- Support local AI models
- Provide natural human interaction
- Support multiple hardware platforms
- Separate intelligence from hardware
- Scale from one room to an entire home

---

## What RoomHub Is

RoomHub is:

- A distributed smart home endpoint platform
- A room intelligence layer
- A unified interaction system
- A local AI interface
- A communication platform

---

## What RoomHub Is Not

RoomHub is not:

- A replacement for Home Assistant
- A dashboard replacement only
- A voice assistant only
- A collection of ESPHome devices
- A hardware-specific solution

Home Assistant remains responsible for device integration and automation.

RoomHub provides the intelligent room experience.

---

## Long Term Vision

A RoomHub-enabled home should feel like one coherent system.

A person should be able to interact naturally:

- Speak to the home
- Ask questions
- Control devices
- Communicate between rooms
- Receive relevant information
- Interact through touch when appropriate

The technology should disappear and the home should simply feel intelligent.
File 2
docs/0002_Architecture.md

Copy this:

# RoomHub Architecture

## Overview

RoomHub follows a distributed architecture.

A central RoomHub Core server provides intelligence, coordination, and services.

Room endpoints provide the physical interaction layer.

             RoomHub Core
          (Central Server)

                |
 ---------------------------------

 |               |               |

Kitchen         Office          Bedroom

Endpoint        Endpoint        Endpoint
---

# RoomHub Core

RoomHub Core is the central intelligence layer.

Responsibilities:

- Room management
- Endpoint management
- AI orchestration
- Audio routing
- Intercom management
- Notifications
- Home Assistant integration
- User context
- Event processing

---

# Room Endpoints

Endpoints are hardware devices located in rooms.

Examples:

- ESP32 devices
- ESP32-P4 panels
- M5Stack Tab5
- Future touchscreen devices

Endpoints provide capabilities:

- Display
- Touch
- Microphone
- Speaker
- Camera
- Sensors

Endpoints do not contain core intelligence.

---

# Capability Model

Every endpoint reports its capabilities.

Example:
Kitchen Endpoint

Capabilities:

Display
Touch
Microphone
Speaker
Camera
Temperature Sensor

The server uses capabilities rather than hardware models.

---

# Room Model

Rooms are first-class objects.

Example:
Kitchen

Devices:

Lights
Speakers
Sensors

Capabilities:

Display
Voice
Intercom

People:

Occupants

Context:

Time
Activity
Presence
Kitchen

Devices:

Lights
Speakers
Sensors

Capabilities:

Display
Voice
Intercom

People:

Occupants

Context:

Time
Activity
Presence

---

# Communication

Communication between RoomHub Core and endpoints will be event-driven.

Examples:

Endpoint events:

- Button pressed
- Voice detected
- Touch interaction
- Sensor update

Server events:

- Display update
- Audio request
- Notification
- Configuration update

---

# Audio Architecture

Audio is managed centrally.

Audio priorities:

1. Emergency announcements
2. Intercom calls
3. Voice assistant
4. Media playback
5. Notifications

Only one service should control a microphone at a time.

---

# AI Architecture

AI services are separate from endpoints.

Possible services:

- Speech-to-text
- Large language model
- Text-to-speech

The AI layer produces intents.

RoomHub decides how those intents are executed.

---

# Home Assistant Integration

Home Assistant remains the device integration layer.

RoomHub communicates with Home Assistant for:

- Device states
- Service calls
- Automations
- Entity information

RoomHub provides:

- Context
- User interaction
- Room intelligence