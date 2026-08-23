import hashlib
import tempfile
import unittest

from app.services.wireless_firmware_service import WirelessFirmwareService


class WirelessFirmwareServiceTests(unittest.TestCase):
    def test_publish_persists_checksum_verified_image(self):
        with tempfile.TemporaryDirectory() as directory:
            service = WirelessFirmwareService(directory)
            image = b"\xe9" + bytes(range(64))
            manifest = service.publish("1.4.1", image)
            self.assertEqual(manifest.version, "1.4.1")
            self.assertEqual(manifest.sha256, hashlib.sha256(image).hexdigest())
            self.assertEqual(service.manifest(), manifest)

    def test_manifest_rejects_content_with_same_size_but_wrong_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            service = WirelessFirmwareService(directory)
            service.publish("1.4.1", b"\xe9original")
            service.image_path.write_bytes(b"\xe9modified")
            self.assertIsNone(service.manifest())

    def test_publish_rejects_non_esp_image(self):
        with tempfile.TemporaryDirectory() as directory:
            service = WirelessFirmwareService(directory)
            with self.assertRaisesRegex(ValueError, "ESP"):
                service.publish("1.4.1", b"invalid")


if __name__ == "__main__":
    unittest.main()
