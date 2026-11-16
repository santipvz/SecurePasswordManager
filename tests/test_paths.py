"""Preserve the desktop data paths used by existing vaults."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from spm.paths import user_data_directory
from spm.vault import default_vault_path


class PathsTests(unittest.TestCase):
    def test_linux_ignores_relative_xdg_paths(self):
        with patch("spm.paths.sys.platform", "linux"), patch.dict(os.environ, XDG_DATA_HOME="data"):
            self.assertEqual(user_data_directory(), Path.home() / ".local" / "share")

    def test_macos_defaults_to_application_support(self):
        with patch("spm.paths.sys.platform", "darwin"), patch.dict(os.environ, XDG_DATA_HOME=""):
            self.assertEqual(user_data_directory(), Path.home() / "Library" / "Application Support")

    def test_absolute_xdg_path_uses_existing_vault_filename(self):
        directory = Path.home() / "custom data"
        for platform in ("linux", "darwin"):
            with (
                self.subTest(platform=platform), patch("spm.paths.sys.platform", platform),
                patch.dict(os.environ, XDG_DATA_HOME=str(directory)),
            ):
                self.assertEqual(default_vault_path(), directory / "SecurePasswordManager" / "vault.spm")

    def test_windows_preserves_custom_override_and_native_directory(self):
        override = Path.home() / "custom data"
        redirected = Path.home() / "redirected data"
        with (
            patch("spm.paths.sys.platform", "win32"),
            patch("spm.paths._windows_known_local_app_data", return_value=str(redirected)),
            patch.dict(os.environ, WIN_PD_OVERRIDE_LOCAL_APPDATA=str(override)),
        ):
            self.assertEqual(user_data_directory(), override)
            with patch.dict(os.environ, WIN_PD_OVERRIDE_LOCAL_APPDATA=""):
                self.assertEqual(user_data_directory(), redirected)

    @unittest.skipUnless(sys.platform == "win32", "Requires the Windows Shell API")
    def test_windows_resolves_known_folder_via_shell_api(self):
        from spm.paths import _windows_known_local_app_data

        location = _windows_known_local_app_data()
        self.assertTrue(location)
        self.assertTrue(Path(location).is_absolute())
