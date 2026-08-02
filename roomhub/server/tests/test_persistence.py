import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app.core import database
from app.core.area_registry import AreaRegistry
from app.core.device_registry import DeviceRegistry
from app.core.entity_registry import EntityRegistry
from app.core.floor_registry import FloorRegistry
from app.events.entity_events import (
    AreaDiscoveredEvent,
    AreaRemovedEvent,
    DeviceDiscoveredEvent,
    DeviceRemovedEvent,
    EntityDiscoveredEvent,
    FloorDiscoveredEvent,
    FloorRemovedEvent,
)


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "roomhub.db"
        self.database_patch = patch.object(database, "DATABASE", self.database_path)
        self.database_patch.start()

    async def asyncTearDown(self):
        self.database_patch.stop()
        self.temp_directory.cleanup()

    async def test_legacy_migration_reload_and_removal(self):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("CREATE TABLE entities (entity_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, name TEXT NOT NULL)")
            connection.execute("INSERT INTO entities VALUES ('light.legacy', 'light', 'Legacy')")

        database.initialise_database()
        floors = FloorRegistry()
        areas = AreaRegistry()
        devices = DeviceRegistry()
        entities = EntityRegistry()
        await floors.handle_discovered(FloorDiscoveredEvent(floor_id="ground", name="Ground", level=0))
        await areas.handle_discovered(AreaDiscoveredEvent(area_id="kitchen", name="Kitchen", floor_id="ground"))
        await devices.handle_discovered(DeviceDiscoveredEvent(device_id="device-1", name="Lamp", area_id="kitchen", config_entries=["entry"]))
        await entities.handle_entity_discovered(EntityDiscoveredEvent(
            entity_id="light.kitchen",
            entity_type="light",
            name="Kitchen Light",
            device_id="device-1",
            area_id="kitchen",
            platform="test",
        ))

        reloaded_floors = FloorRegistry()
        reloaded_areas = AreaRegistry()
        reloaded_devices = DeviceRegistry()
        reloaded_entities = EntityRegistry()
        reloaded_floors.load()
        reloaded_areas.load()
        reloaded_devices.load()
        reloaded_entities.load()
        self.assertEqual(reloaded_floors.get("ground").level, 0)
        self.assertEqual(reloaded_areas.get("kitchen").floor_id, "ground")
        self.assertEqual(reloaded_devices.get("device-1").config_entries, ["entry"])
        self.assertEqual(reloaded_entities.get("light.kitchen").device_id, "device-1")
        self.assertEqual(reloaded_entities.get("light.legacy").integration, "homeassistant")

        await floors.handle_removed(FloorRemovedEvent(floor_id="ground"))
        await areas.handle_removed(AreaRemovedEvent(area_id="kitchen"))
        await devices.handle_removed(DeviceRemovedEvent(device_id="device-1"))
        reloaded_floors.load()
        reloaded_areas.load()
        reloaded_devices.load()
        self.assertEqual(reloaded_floors.get_all(), {})
        self.assertEqual(reloaded_areas.get_all(), {})
        self.assertEqual(reloaded_devices.get_all(), {})
