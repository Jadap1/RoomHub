from __future__ import annotations

from typing import Any

from aiohttp import ClientSession


class RoomHubApiError(Exception):
    """Raised when the RoomHub API cannot satisfy a request."""


class RoomHubApi:
    def __init__(self, session: ClientSession, base_url: str) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def endpoints(self) -> dict[str, dict[str, Any]]:
        data = await self._request("GET", "/endpoints")
        if not isinstance(data, dict):
            raise RoomHubApiError("RoomHub returned invalid endpoint data")
        return data

    async def control(
        self,
        endpoint_id: str,
        *,
        screen_on: bool | None = None,
        volume: int | None = None,
        microphone_muted: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if screen_on is not None:
            payload["screen_on"] = screen_on
        if volume is not None:
            payload["volume"] = volume
        if microphone_muted is not None:
            payload["microphone_muted"] = microphone_muted
        return await self._request(
            "PUT", f"/api/endpoints/{endpoint_id}/controls", json=payload
        )

    async def camera_image(self, endpoint_id: str) -> bytes:
        try:
            async with self._session.get(
                f"{self.base_url}/api/endpoints/{endpoint_id}/camera/snapshot",
                timeout=20,
            ) as response:
                if response.status >= 400:
                    raise RoomHubApiError(
                        f"RoomHub returned HTTP {response.status}"
                    )
                if response.content_type != "image/jpeg":
                    raise RoomHubApiError("RoomHub returned an invalid camera image")
                return await response.read()
        except RoomHubApiError:
            raise
        except Exception as error:
            raise RoomHubApiError(str(error)) from error

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with self._session.request(
                method, f"{self.base_url}{path}", **kwargs
            ) as response:
                if response.status >= 400:
                    raise RoomHubApiError(
                        f"RoomHub returned HTTP {response.status}"
                    )
                return await response.json()
        except RoomHubApiError:
            raise
        except Exception as error:
            raise RoomHubApiError(str(error)) from error
