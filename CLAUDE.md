# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IoTuring is a cross-platform Python application that monitors PC statistics and sends them to integrations (MQTT, HomeAssistant) or displays them on console. It uses a modular plugin architecture with **Entities** (data sources) and **Warehouses** (data sinks).

- **Platforms**: Windows, Linux, macOS, OpenBSD
- **Python**: 3.8+
- **Versioning**: Calendar versioning (YYYY.M.n)

## Commands

```bash
# Development setup (editable install)
pip install -e .

# With venv
python -m venv .venv && . ./.venv/bin/activate && pip install -e .

# Run tests (Docker - recommended)
docker run --rm -it $(docker build -q -f tests.Dockerfile .)

# Run tests (local)
pip install -e ".[test]"
python -m pytest

# Run application
IoTuring           # Normal mode
IoTuring -c        # Configuration mode
IoTuring -o        # Open config file in editor

# Build Docker image
docker build -t ioturing:latest .
```

**Environment variables:**
- `IOTURING_CONFIG_DIR`: Config directory path
- `IOTURING_LOG_LEVEL`: Log level (e.g., `LOG_DEBUG`)

## Architecture

### Core Data Flow

```
Entity (collects sensor data via Update())
    ↓
EntityManager (singleton, manages all active entities)
    ↓
Warehouse (reads sensors, publishes to external systems via Loop())
    ↓
External Systems (MQTT broker, HomeAssistant, Console)
```

Commands flow in reverse: Warehouse receives commands → triggers Entity command callbacks.

### Key Components

**Entity** (`IoTuring/Entity/Entity.py`): Base class for data sources. Subclasses implement:
- `Initialize()`: Register sensors/commands
- `Update()`: Periodic data collection (runs in dedicated thread)
- Optional: `CheckSystemSupport()`: Raise exception if OS not supported

**Warehouse** (`IoTuring/Warehouse/Warehouse.py`): Base class for data sinks. Subclasses implement:
- `Loop()`: Periodic warehouse operations (runs in dedicated thread)

**EntityData** (`IoTuring/Entity/EntityData.py`):
- `EntitySensor`: Read-only data published to warehouses
- `EntityCommand`: Writable commands received from warehouses

**ClassManager** (`IoTuring/ClassManager/`): Dynamically discovers and loads Entity/Warehouse classes from filesystem without hardcoded imports. Classes are discovered by matching folder names.

**Configurator** (`IoTuring/Configurator/`): Interactive YAML-based configuration using InquirerPy.

### Threading Model

- Main thread: Initialization and event loop
- One daemon thread per Entity for periodic `Update()` calls
- One daemon thread per Warehouse for periodic `Loop()` calls

### Plugin Architecture

New entities/warehouses are added by creating a folder with matching class name:
- Entities: `IoTuring/Entity/Deployments/<EntityName>/<EntityName>.py`
- Warehouses: `IoTuring/Warehouse/Deployments/<WarehouseName>/<WarehouseName>.py`

No import registration needed - ClassManager discovers them automatically.

## Creating a New Entity

```python
from IoTuring.Entity.Entity import Entity
from IoTuring.Entity.EntityData import EntitySensor

KEY_MY_SENSOR = 'my_sensor'

class MyEntity(Entity):
    NAME = "MyEntity"

    def Initialize(self):
        self.RegisterEntitySensor(EntitySensor(self, KEY_MY_SENSOR))

    def Update(self):
        self.SetEntitySensorValue(KEY_MY_SENSOR, "value")

    @classmethod
    def CheckSystemSupport(cls):
        # Raise cls.UnsupportedOsException() if OS not supported
        pass
```

For configuration support, implement `ConfigurationPreset()` classmethod returning a `MenuPreset`.

## Logging

Inherit from `LogObject` and use:
```python
self.Log(self.LOG_DEBUG, "message")
self.Log(self.LOG_INFO, "message")
self.Log(self.LOG_WARNING, "message")
self.Log(self.LOG_ERROR, "message")
```

## Running External Commands

Use the `RunCommand()` helper from Entity base class:
```python
result = self.RunCommand(
    ["command", "args"],
    command_name="descriptive_name",
    log_errors=True,
    capture_output=True
)
```

## Config File Location

- Linux/macOS: `~/.config/IoTuring/config.yaml`
- Windows: `%APPDATA%/IoTuring/config.yaml`

## InquirerPy Note

PyPI version has import issues. For development, install from GitHub:
```bash
pip uninstall InquirerPy
pip install git+https://github.com/kazhala/InquirerPy
```
