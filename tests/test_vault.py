"""Exercise the vault's persistence and security boundaries."""

import errno
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spm.vault import Entry, Vault, VaultConflict, VaultError, read_legacy

MASTER = "Una frase de prueba larga"
NEW_MASTER = "Otra frase de prueba larga"
ENTRY = Entry(
    name="Correo privado", username="ana@example.org", password="clave-de-ejemplo-903!",
    url="https://example.org", notes="Recuperación\nCuenta privada",
)


class VaultTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(folder) / "private" / "vault.spm"
        Vault.create(self.path, MASTER)
        self.vault = Vault(self.path, MASTER)

    def test_encrypted_round_trip_and_mutations(self):
        initial = self.path.read_bytes()
        self.vault.add([ENTRY])
        encrypted = self.path.read_bytes()
        for plaintext in (ENTRY.name, ENTRY.username, ENTRY.password, ENTRY.url, "Cuenta privada"):
            self.assertNotIn(plaintext.encode(), encrypted)
        self.assertEqual(initial[:20], encrypted[:20])
        self.assertNotEqual(initial[20:32], encrypted[20:32])
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

        vault = Vault(self.path, MASTER)
        self.assertEqual(vault.list("EXAMPLE.ORG"), [ENTRY])
        self.assertEqual(vault.get(" correo PRIVADO "), ENTRY)
        renamed = Entry("Trabajo", ENTRY.password)
        vault.edit(ENTRY.name, renamed)
        self.assertEqual(Vault(self.path, MASTER).list(), [renamed])
        vault.delete("trabajo")
        self.assertEqual(Vault(self.path, MASTER).list(), [])

    def test_rejects_wrong_master_and_modifications(self):
        self.vault.add([ENTRY])
        original = self.path.read_bytes()
        with self.assertRaisesRegex(VaultError, "[Ii]ncorrect"):
            Vault(self.path, NEW_MASTER)
        for offset in (4, 20, 32, len(original) - 1):
            with self.subTest(offset=offset):
                tampered = bytearray(original)
                tampered[offset] ^= 1
                self.path.write_bytes(tampered)
                with self.assertRaisesRegex(VaultError, "tampered with"):
                    Vault(self.path, MASTER)
                self.assertEqual(self.path.read_bytes(), tampered)
        self.path.write_bytes(original[:20])
        with self.assertRaisesRegex(VaultError, "vault format"):
            Vault(self.path, MASTER)

    def test_master_rotation_and_recovery_from_backup(self):
        self.vault.add([ENTRY])
        backup = self.path.with_name("backup.spm")
        self.vault.backup(backup)
        with self.assertRaisesRegex(VaultError, "backup destination"):
            self.vault.backup(backup)
        with self.assertRaisesRegex(VaultError, "[Ii]ncorrect"):
            self.vault.verify_master(NEW_MASTER)
        self.vault.verify_master(MASTER)
        self.vault.change_master(NEW_MASTER)
        self.assertNotEqual(backup.read_bytes()[4:20], self.path.read_bytes()[4:20])
        with self.assertRaisesRegex(VaultError, "[Ii]ncorrect"):
            Vault(self.path, MASTER)
        self.assertEqual(Vault(self.path, NEW_MASTER).list(), [ENTRY])
        self.assertEqual(Vault(backup, MASTER).list(), [ENTRY])

    def test_failed_write_and_conflicting_snapshots_keep_original(self):
        stale = Vault(self.path, MASTER)
        self.vault.add([ENTRY])
        before = self.path.read_bytes()
        with self.assertRaises(VaultConflict):
            stale.add([Entry("Otra cuenta", "otra-clave")])
        with self.assertRaises(VaultConflict):
            stale.backup(self.path.with_name("stale.spm"))
        with patch("spm.adapters.vault_files.Path.replace", side_effect=OSError("rename failed")):
            with self.assertRaises(OSError):
                self.vault.delete(ENTRY.name)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.vault.list(), [ENTRY])
        self.assertEqual(list(self.path.parent.glob(".spm-*")), [])

    def test_create_does_not_overwrite_existing_data(self):
        original = self.path.read_bytes()
        with self.assertRaisesRegex(VaultError, "already exists"):
            Vault.create(self.path, NEW_MASTER)
        self.assertEqual(self.path.read_bytes(), original)
        with self.assertRaisesRegex(VaultError, "15 characters"):
            Vault.create(self.path.with_name("new.spm"), "too short")

    @unittest.skipUnless(os.name == "posix", "POSIX hard-link fallback")
    def test_backup_on_filesystems_without_hard_links(self):
        backup = self.path.with_name("backup.spm")
        with patch("spm.adapters.vault_files.os.link", side_effect=OSError(errno.ENOTSUP, "unsupported")):
            self.vault.backup(backup)
            with self.assertRaisesRegex(VaultError, "backup destination"):
                self.vault.backup(backup)
        self.assertEqual(self.path.read_bytes(), backup.read_bytes())
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)

    def test_legacy_import_is_atomic_and_keeps_the_originals(self):
        source = self.path.with_name("Cuenta.key")
        original = "User: ñ@example.org\r\nPassword: <@0-=)>\r\n".encode()
        source.write_bytes(original)
        invalid = self.path.with_name("invalid.key")
        invalid.write_bytes(b"not a credential")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(VaultError, "does not contain"):
            self.vault.add(read_legacy(path) for path in (source, invalid))
        self.assertEqual(self.path.read_bytes(), before)
        self.vault.add([read_legacy(source)])
        self.assertEqual(self.vault.get("cuenta"), Entry("Cuenta", "<@0-=)>", "ñ@example.org"))
        with self.assertRaisesRegex(VaultError, "already exists"):
            self.vault.add([Entry("CUENTA", "otro-valor")])
        self.assertEqual(source.read_bytes(), original)
