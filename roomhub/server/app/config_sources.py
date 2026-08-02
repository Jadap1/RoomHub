import json
import os
from pathlib import Path
from typing import Any


DEFAULT_OPTIONS_PATH = Path("/data/options.json")


def is_homeassistant_app() -> bool:

    return (
        os.getenv("ROOMHUB_RUNTIME_MODE")
        == "homeassistant_app"
        and bool(os.getenv("SUPERVISOR_TOKEN"))
    )


def load_app_options() -> dict[str, Any]:

    options_path = Path(
        os.getenv(
            "ROOMHUB_OPTIONS_PATH",
            str(DEFAULT_OPTIONS_PATH)
        )
    )

    if not options_path.exists():

        raise RuntimeError(
            "RoomHub App options file not found: "
            f"{options_path}"
        )

    with options_path.open(
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)