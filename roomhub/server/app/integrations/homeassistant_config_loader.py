import json
from pathlib import Path

from .homeassistant_config import HomeAssistantConfig


CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "homeassistant.json"
)


def load_homeassistant_config() -> HomeAssistantConfig:

    if not CONFIG_PATH.exists():

        raise RuntimeError(
            "Home Assistant configuration file not found: "
            f"{CONFIG_PATH}"
        )


    with CONFIG_PATH.open(
        "r",
        encoding="utf-8"
    ) as file:

        raw_config = json.load(file)


    return HomeAssistantConfig.model_validate(
        raw_config
    )