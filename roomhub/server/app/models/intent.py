from typing import Literal

from pydantic import BaseModel


class ResolvedEntityIntent(BaseModel):
    action: Literal["entity.command"] = "entity.command"
    entity_id: str
    command: Literal["turn_on", "turn_off", "toggle"]
    transcript: str
    area_id: str | None = None


class IntentResolutionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        candidates: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.candidates = candidates or []
