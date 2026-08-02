import os
from dataclasses import dataclass

from ..config_sources import (
    is_homeassistant_app,
    load_app_options,
)
from .homeassistant_config_loader import load_homeassistant_config


@dataclass(frozen=True)
class HomeAssistantConnectionSettings:

    websocket_url: str
    access_token: str
    mode: str


def get_homeassistant_connection_settings(
) -> HomeAssistantConnectionSettings:

    if is_homeassistant_app():

        token = os.getenv("SUPERVISOR_TOKEN")

        if not token:

            raise RuntimeError(
                "SUPERVISOR_TOKEN is unavailable"
            )

        return HomeAssistantConnectionSettings(
            websocket_url="ws://supervisor/core/websocket",
            access_token=token,
            mode="homeassistant_app"
        )

    config = load_homeassistant_config()

    websocket_url = (
        config.url
        .rstrip("/")
        .replace("https://", "wss://")
        .replace("http://", "ws://")
        + "/api/websocket"
    )

    return HomeAssistantConnectionSettings(
        websocket_url=websocket_url,
        access_token=config.access_token,
        mode="local_development"
    )


def get_homeassistant_assist_pipeline_name() -> str:

    if is_homeassistant_app():
        return str(
            load_app_options().get(
                "assist_pipeline_name",
                "RoomHub Local"
            )
        )

    return (
        load_homeassistant_config()
        .assist_pipeline_name
    )
