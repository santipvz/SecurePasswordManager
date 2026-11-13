"""Verify the command-line entry point avoids accidental secret disclosure."""

import contextlib
import getpass
import io
import string
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

from spm.console_interface import main
from spm.vault import Entry, KeyEnrollment, Vault

MASTER = "Frase maestra de prueba"
PASSWORD = "contraseña privada 827@"


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.vault = str(Path(directory) / "vault.spm")

    def run_command(self, *args, secrets=()):
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch("spm.console_interface.getpass.getpass", side_effect=secrets),
            contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors),
        ):
            result = main(["--vault", self.vault, *args])
        return result, output.getvalue(), errors.getvalue()

    def test_generator_is_independent_of_vault_and_validates_length(self):
        code, output, _ = self.run_command("generate", "--length", "32", "--no-symbols")
        self.assertEqual(code, 0)
        password = output.rstrip("\n")
        self.assertEqual(len(password), 32)
        self.assertTrue(password.isascii() and password.isalnum())
        for group in (string.ascii_lowercase, string.ascii_uppercase, string.digits):
            self.assertTrue(any(character in group for character in password))
        code, output, _ = self.run_command("generate", "--length", "11")
        self.assertEqual((code, output), (1, ""))

    def test_crud_and_explicit_password_reveal(self):
        code, _, _ = self.run_command("init", secrets=(MASTER, MASTER))
        self.assertEqual(code, 0)
        code, output, errors = self.run_command(
            "add", "Correo", "--username", "ana", secrets=(MASTER, PASSWORD),
        )
        self.assertEqual(code, 0)
        self.assertNotIn(PASSWORD, output + errors)
        code, output, _ = self.run_command("edit", "correo", "--username", "otra", secrets=(MASTER,))
        self.assertEqual(code, 0)
        code, output, _ = self.run_command("show", "correo", secrets=(MASTER,))
        self.assertEqual(code, 0)
        self.assertIn("Name: Correo", output)
        self.assertIn("Username: otra", output)
        self.assertNotIn(PASSWORD, output)
        code, output, _ = self.run_command("show", "Correo", "--password", secrets=(MASTER,))
        self.assertEqual((code, output), (0, PASSWORD + "\n"))
        code, _, _ = self.run_command("delete", "Correo", "-y", secrets=(MASTER,))
        self.assertEqual(code, 0)
        code, output, _ = self.run_command("list", secrets=(MASTER,))
        self.assertEqual((code, output), (0, ""))

    def test_password_prompt_aborts_if_terminal_cannot_hide_input(self):
        def no_echo_unavailable(_prompt):
            warnings.warn("no echo", getpass.GetPassWarning)
            self.fail("The command should abort before reading echoed input.")

        errors = io.StringIO()
        with (
            patch("spm.console_interface.getpass.getpass", side_effect=no_echo_unavailable),
            contextlib.redirect_stderr(errors),
        ):
            self.assertEqual(main(["--vault", self.vault, "init"]), 1)
        self.assertIn("hide password input", errors.getvalue())
        self.assertFalse(Path(self.vault).exists())

    def test_audit_reports_findings_without_exposing_or_writing_passwords(self):
        path = Path(self.vault)
        Vault.create(path, MASTER)
        code, output, _ = self.run_command("audit", secrets=(MASTER,))
        self.assertEqual((code, output), (0, "The vault is empty.\n"))

        short_password = "ejemplo-breve"
        vault = Vault(path, MASTER)
        vault.add([Entry("Correo", PASSWORD), Entry("Foro", PASSWORD),
                   Entry("Tienda", short_password)])
        original = path.read_bytes()
        code, output, errors = self.run_command("audit", secrets=(MASTER,))
        self.assertEqual(code, 0)
        self.assertIn("Fewer than 15 characters:\n  - Tienda", output)
        self.assertIn("Group 1\n    - Correo\n    - Foro", output)
        self.assertNotIn(PASSWORD, output + errors)
        self.assertNotIn(short_password, output + errors)
        self.assertEqual(path.read_bytes(), original)

    def test_security_key_can_unlock_without_prompting_for_master(self):
        path = Path(self.vault)
        Vault.create(path, MASTER)
        Vault(path, MASTER).add([Entry("Correo", PASSWORD)])
        enrollment = KeyEnrollment(b"credential", b"s" * 32, b"k" * 32)
        hardware = MagicMock()
        key = hardware.__enter__.return_value
        key.enroll.return_value = enrollment
        key.derive.return_value = enrollment.secret

        with patch("spm.console_interface.open_security_key", return_value=hardware):
            code, _, _ = self.run_command("key-add", secrets=(MASTER,))
            self.assertEqual(code, 0)
            code, output, _ = self.run_command("--security-key", "list")
            self.assertEqual((code, output), (0, "Correo\n"))
            code, _, _ = self.run_command("--security-key", "key-remove")
            self.assertEqual(code, 1)
            code, _, _ = self.run_command("key-remove", secrets=(MASTER,))
            self.assertEqual(code, 0)
        self.assertFalse(Vault(path, MASTER).has_security_key)
