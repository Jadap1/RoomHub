import json
from contextlib import closing

from ..events.entity_events import (
    DeviceDiscoveredEvent,
    DeviceRemovedEvent,
)
from ..models.device import Device
from .database import get_connection


class DeviceRegistry:

    def __init__(self) -> None:
        self.devices: dict[str, Device] = {}


    def get(
        self,
        device_id: str
    ) -> Device | None:

        return self.devices.get(device_id)


    def get_all(self) -> dict[str, dict]:

        return {
            key: value.model_dump()
            for key, value in self.devices.items()
        }


    def load(self) -> None:

        with closing(get_connection()) as connection, connection:
            rows = connection.execute(
                """
                SELECT device_id, name, area_id,
                       manufacturer, model,
                       config_entries, via_device_id
                FROM devices
                """
            ).fetchall()

        self.devices = {
            row[0]: Device(
                device_id=row[0],
                name=row[1],
                area_id=row[2],
                manufacturer=row[3],
                model=row[4],
                config_entries=json.loads(row[5]),
                via_device_id=row[6]
            )
            for row in rows
        }


    def save(self, device: Device) -> None:

        with closing(get_connection()) as connection, connection:
            connection.execute(
                """
                INSERT INTO devices
                (
                    device_id, name, area_id,
                    manufacturer, model,
                    config_entries, via_device_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    name = excluded.name,
                    area_id = excluded.area_id,
                    manufacturer = excluded.manufacturer,
                    model = excluded.model,
                    config_entries = excluded.config_entries,
                    via_device_id = excluded.via_device_id
                """,
                (
                    device.device_id,
                    device.name,
                    device.area_id,
                    device.manufacturer,
                    device.model,
                    json.dumps(device.config_entries),
                    device.via_device_id
                )
            )


    async def handle_discovered(
        self,
        event: DeviceDiscoveredEvent
    ) -> None:

        device = Device(
            device_id=event.device_id,
            name=event.name,
            area_id=event.area_id,
            manufacturer=event.manufacturer,
            model=event.model,
            config_entries=event.config_entries,
            via_device_id=event.via_device_id
        )
        self.devices[event.device_id] = device
        self.save(device)


    async def handle_removed(
        self,
        event: DeviceRemovedEvent
    ) -> None:

        self.devices.pop(
            event.device_id,
            None
        )

        with closing(get_connection()) as connection, connection:
            connection.execute(
                "DELETE FROM devices WHERE device_id = ?",
                (event.device_id,)
            )


device_registry = DeviceRegistry()
