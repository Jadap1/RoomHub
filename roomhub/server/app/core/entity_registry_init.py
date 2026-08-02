from .entity_registry import entity_registry
from ..models.entity import Entity


def register_entities():

    existing = entity_registry.get(
        "light.kitchen_main"
    )

    if existing is not None:
        existing.integration = "roomhub"
        entity_registry.save(existing)
        return

    entity_registry.register(
        Entity(
            entity_id="light.kitchen_main",
            entity_type="light",
            name="Kitchen Main Light",
            integration="roomhub",
            capabilities=[
                "on_off"
            ]
        )
    )
