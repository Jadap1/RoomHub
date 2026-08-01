from .entity_registry import entity_registry
from ..models.entity import Entity


def register_entities():

    if entity_registry.get("light.kitchen_main") is not None:
        return

    entity_registry.register(
        Entity(
            entity_id="light.kitchen_main",
            entity_type="light",
            name="Kitchen Main Light",
            capabilities=[
                "on_off"
            ]
        )
    )