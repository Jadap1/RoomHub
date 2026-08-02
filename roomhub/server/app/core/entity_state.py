from datetime import UTC, datetime


class EntityState:

    def __init__(
        self,
        state=None,
        attributes=None,
        available=True,
        last_updated=None
    ):

        self.state = state
        self.attributes = attributes or {}
        self.available = available
        self.last_updated = (
            last_updated
            if last_updated is not None
            else datetime.now(UTC)
        )


    def update(
        self,
        state,
        attributes=None
    ):

        self.state = state

        if attributes:
            self.attributes.update(attributes)

        self.last_updated = datetime.now(UTC)


    def as_dict(self):

        return {
            "state": self.state,
            "attributes": self.attributes,
            "available": self.available,
            "last_updated": self.last_updated.isoformat()
        }
