import hmac
import os

from ..config_sources import load_app_options


def configured_firmware_token() -> str | None:
    environment_token = os.getenv("ROOMHUB_FIRMWARE_ADMIN_TOKEN", "").strip()
    if environment_token:
        return environment_token
    try:
        option_token = str(
            load_app_options().get("firmware_admin_token", "")
        ).strip()
    except RuntimeError:
        return None
    return option_token or None


def firmware_token_valid(candidate: str | None) -> bool:
    configured = configured_firmware_token()
    return bool(
        configured
        and candidate
        and hmac.compare_digest(configured, candidate)
    )
