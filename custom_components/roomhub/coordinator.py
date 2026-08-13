from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RoomHubApi, RoomHubApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class RoomHubCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, api: RoomHubApi) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=10),
            always_update=False,
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.endpoints()
        except RoomHubApiError as error:
            raise UpdateFailed(str(error)) from error
