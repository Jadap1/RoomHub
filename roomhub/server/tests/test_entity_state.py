import unittest
from datetime import UTC

from app.core.entity_state import EntityState


class EntityStateTests(unittest.TestCase):
    def test_timestamps_are_timezone_aware_utc(self):
        state = EntityState(state="off")
        initial_timestamp = state.last_updated

        self.assertEqual(initial_timestamp.tzinfo, UTC)
        self.assertTrue(
            state.as_dict()["last_updated"].endswith(
                "+00:00"
            )
        )

        state.update("on")

        self.assertEqual(state.last_updated.tzinfo, UTC)
        self.assertGreaterEqual(
            state.last_updated,
            initial_timestamp
        )
