import hashlib
import tempfile
import unittest
from pathlib import Path

from app.services.firmware_service import FirmwareService, MAX_FIRMWARE_BYTES


class FirmwareServiceTests(unittest.TestCase):
    def test_publish_persists_verified_manifest_and_image(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FirmwareService(directory)
            image = b"\xe9" + bytes(range(64))

            manifest = service.publish("0.2.1", image)

            self.assertEqual(manifest.version, "0.2.1")
            self.assertEqual(manifest.size, len(image))
            self.assertEqual(manifest.sha256, hashlib.sha256(image).hexdigest())
            self.assertEqual(service.image_path.read_bytes(), image)
            self.assertEqual(service.manifest(), manifest)

    def test_publish_rejects_non_esp_image(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FirmwareService(directory)
            with self.assertRaisesRegex(ValueError, "ESP"):
                service.publish("0.2.1", b"invalid")

    def test_publish_rejects_oversized_image(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FirmwareService(directory)
            with self.assertRaisesRegex(ValueError, "size"):
                service.publish("0.2.1", b"\xe9" + bytes(MAX_FIRMWARE_BYTES))

    def test_manifest_rejects_mismatched_file_size(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FirmwareService(directory)
            service.publish("0.2.1", b"\xe9image")
            service.image_path.write_bytes(b"\xe9changed")
            self.assertIsNone(service.manifest())


if __name__ == "__main__":
    unittest.main()
