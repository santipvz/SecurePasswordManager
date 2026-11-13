"""Check that the desktop clears a revealed password before locking."""

import tempfile
import unittest
from pathlib import Path

from spm.desktop_interface import DesktopApp, tk, ttk
from spm.vault import Entry, Vault


@unittest.skipIf(tk is None, "Tkinter is unavailable")
class DesktopLockTests(unittest.TestCase):
    def test_lock_removes_revealed_password_and_copy_controls(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No graphical display: {error}")
        self.addCleanup(root.destroy)

        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory) / "vault.spm"
        master = "Synthetic desktop test passphrase"
        entry = Entry("Sample account", "synthetic sample password")
        Vault.create(path, master)
        app = DesktopApp(root, path)
        app.vault = Vault(path, master)
        app.vault.add([entry])
        app._show_vault()
        app._refresh(select=entry.name)
        root.update()
        app._reveal(entry.password)
        self.assertEqual(app.password_display.get(), entry.password)

        unlocked_view = app.view
        app.lock()

        self.assertFalse(unlocked_view.winfo_exists())
        self.assertIsNone(app.vault)
        self.assertIsNone(app.reveal_timer)
        labels = [child.cget("text") for child in app.view.winfo_children()
                  if isinstance(child, ttk.Label)]
        self.assertIn("Unlock your vault", labels)
