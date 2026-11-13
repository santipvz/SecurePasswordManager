"""Open and update fixed, synthetic vaults generated before the core refactor."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from spm.vault import Entry, Vault

FIXTURES = Path(__file__).parent / "fixtures"
MASTER = "Synthetic compatibility passphrase"
ENTRY = Entry("Fixture account", "synthetic password only", "fixture@example.test",
              "https://example.test", "Synthetic data only.")


class VaultCompatibilityTests(unittest.TestCase):
    def test_previous_formats_open_and_can_be_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, version, has_key in (
                ("password-v1.spm", b"SPM\x01", False), ("fido2-v2.spm", b"SPM\x02", True),
            ):
                with self.subTest(name=name):
                    path = Path(directory) / name
                    shutil.copyfile(FIXTURES / name, path)
                    original = path.read_bytes()
                    vault = Vault(path, MASTER)
                    self.assertEqual(vault.list(), [ENTRY])
                    self.assertEqual(vault.has_security_key, has_key)
                    self.assertEqual(path.read_bytes(), original)
                    updated = Entry("Added account", "another synthetic password")
                    vault.add([updated])
                    self.assertEqual(path.read_bytes()[:4], version)
                    self.assertEqual(Vault(path, MASTER).list(), [updated, ENTRY])

    def test_previous_fido2_registration_still_unlocks(self):
        device = Mock()
        device.derive.return_value = b"T" * 32
        vault = Vault(FIXTURES / "fido2-v2.spm", security_key=device)
        self.assertEqual(vault.list(), [ENTRY])
        device.derive.assert_called_once_with(b"synthetic credential", bytes(range(32)))
