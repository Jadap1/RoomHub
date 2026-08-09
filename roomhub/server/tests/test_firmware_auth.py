import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.firmware_audit import FirmwareAuditLog
from app.services.firmware_auth import firmware_token_valid


class FirmwareSecurityTests(unittest.TestCase):
    def test_token_comparison_requires_configured_exact_value(self):
        with patch.dict(
            "os.environ",
            {"ROOMHUB_FIRMWARE_ADMIN_TOKEN": "correct-token"},
        ):
            self.assertTrue(firmware_token_valid("correct-token"))
            self.assertFalse(firmware_token_valid("wrong-token"))
            self.assertFalse(firmware_token_valid(None))

    def test_audit_log_appends_json_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            audit = FirmwareAuditLog(path)
            audit.record("published", version="0.3.0")
            audit.record("deployed", endpoint_id="tab5-01")
            entries = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([entry["action"] for entry in entries], [
                "published",
                "deployed",
            ])


if __name__ == "__main__":
    unittest.main()
