import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app.core import database
from app.services.endpoint_pairing_service import EndpointPairingService


class EndpointPairingServiceTests(unittest.TestCase):
    def test_code_is_single_use_and_binds_endpoint(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            database, "DATABASE", Path(directory) / "roomhub.db"
        ):
            database.initialise_database()
            service = EndpointPairingService()
            created = service.create("Kitchen Display", "kitchen")
            token = created["pairing_token"]

            paired = service.authenticate("tab5-a1b2c3", token)
            self.assertTrue(paired.accepted)
            self.assertEqual(paired.reason, "paired")
            self.assertEqual(paired.device_name, "Kitchen Display")
            self.assertEqual(paired.area_id, "kitchen")

            self.assertFalse(
                service.authenticate("different-endpoint", token).accepted
            )
            self.assertTrue(
                service.authenticate("tab5-a1b2c3", token).accepted
            )
            self.assertFalse(
                service.authenticate("tab5-a1b2c3", "wrong-token").accepted
            )

    def test_unassigned_endpoint_requires_pairing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            database, "DATABASE", Path(directory) / "roomhub.db"
        ):
            database.initialise_database()
            result = EndpointPairingService().authenticate("unknown", None)
            self.assertFalse(result.accepted)
            self.assertEqual(result.reason, "pairing_required")

    def test_pre_pairing_assignment_is_grandfathered(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            database, "DATABASE", Path(directory) / "roomhub.db"
        ):
            database.initialise_database()
            with closing(database.get_connection()) as connection, connection:
                connection.execute(
                    "INSERT INTO endpoint_assignments VALUES (?, ?)",
                    ("existing", "bedroom"),
                )
            result = EndpointPairingService().authenticate("existing", None)
            self.assertTrue(result.accepted)
            self.assertTrue(result.legacy)


if __name__ == "__main__":
    unittest.main()
