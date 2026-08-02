from fnmatch import fnmatch
from typing import Literal

from pydantic import BaseModel, Field


class EntityFilterConfig(BaseModel):

    mode: Literal["all", "include", "exclude"] = "all"

    patterns: list[str] = Field(
        default_factory=list
    )

    always_include: list[str] = Field(
        default_factory=list
    )

    always_exclude: list[str] = Field(
        default_factory=list
    )


    def allows(self, entity_id: str) -> bool:

        if self.mode == "all":
            allowed = True

        elif self.mode == "include":
            allowed = any(
                fnmatch(entity_id, pattern)
                for pattern in self.patterns
            )

        else:
            allowed = not any(
                fnmatch(entity_id, pattern)
                for pattern in self.patterns
            )


        if any(
            fnmatch(entity_id, pattern)
            for pattern in self.always_include
        ):
            allowed = True


        if any(
            fnmatch(entity_id, pattern)
            for pattern in self.always_exclude
        ):
            allowed = False


        return allowed


class HomeAssistantConfig(BaseModel):

    url: str

    access_token: str

    reconnect_delay_seconds: int = 5

    entity_filter: EntityFilterConfig = Field(
        default_factory=EntityFilterConfig
    )