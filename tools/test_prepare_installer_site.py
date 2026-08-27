import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_installer_site import prepare


class PrepareInstallerSiteTests(unittest.TestCase):
    def test_copies_firmware_and_rewrites_manifest_to_same_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "release"
            installer = root / "installer"
            release.mkdir()
            installer.mkdir()
            firmware = "roomhub-tab5-0.7.55-factory.bin"
            (release / firmware).write_bytes(b"signed firmware")
            (release / "manifest.json").write_text(json.dumps({
                "builds": [{"parts": [{
                    "path": "https://github.com/example/release/" + firmware,
                    "offset": 0,
                }]}],
            }), encoding="utf-8")

            prepare(release, installer)

            result = json.loads(
                (installer / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["builds"][0]["parts"][0]["path"], firmware)
            self.assertEqual((installer / firmware).read_bytes(), b"signed firmware")


if __name__ == "__main__":
    unittest.main()
