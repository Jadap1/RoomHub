from .entity_registry import entity_registry
from ..models.entity import Entity


def register_entities():

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