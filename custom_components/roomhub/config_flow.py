from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RoomHubApi, RoomHubApiError
from .const import DEFAULT_URL, DOMAIN


class RoomHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            try:
                health = await RoomHubApi(
                    async_get_clientsession(self.hass), url
                ).health()
                if health.get("service") != "RoomHub":
                    raise RoomHubApiError("Unexpected service")
            except RoomHubApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="RoomHub", data={CONF_URL: url})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_URL, default=DEFAULT_URL): str}
            ),
            errors=errors,
        )
