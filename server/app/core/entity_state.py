from datetime import datetime


class EntityState:

    def __init__(
        self,
        state=None,
        attributes=None,
        available=True
    ):

        self.state = state
        self.attributes = attributes or {}
        self.available = available
        self.last_updated = datetime.utcnow()


    def update(
        self,
        state,
        attributes=None
    ):

        self.state = state

        if attributes:
            self.attributes.update(attributes)

        self.last_updated = datetime.utcnow()


    def as_dict(self):

        return {
            "state": self.state,
            "attributes": self.attributes,
            "available": self.available,
            "last_updated": self.last_updated.isoformat()
        }