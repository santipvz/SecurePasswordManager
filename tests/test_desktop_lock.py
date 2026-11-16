"""Check that the desktop clears a revealed password before locking."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from spm.desktop_interface import LOCK_AFTER, DesktopApp, tk, ttk
from spm.vault import Entry, Vault


class IdleTimeoutTests(unittest.TestCase):
    def test_sleep_and_late_input_cannot_extend_the_unlocked_session(self):
        for current in ((20.0, 120.5), (10.0 + LOCK_AFTER, 110.0 + LOCK_AFTER)):
            with self.subTest(current=current):
                app = DesktopApp.__new__(DesktopApp)
                app.last_activity = (10.0, 110.0)
                app.vault = object()
                app.lock = Mock()
                with patch("spm.desktop_interface._session_time", return_value=current):
                    self.assertEqual(app._record_activity(), "break")
                app.lock.assert_called_once_with()
                self.assertEqual(app.last_activity, (10.0, 110.0))


@unittest.skipIf(tk is None, "Tkinter is unavailable")
class DesktopLockTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No graphical display: {error}")
        self.addCleanup(self.root.destroy)

        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "vault.spm"
        self.master = "Synthetic desktop test passphrase"
        Vault.create(self.path, self.master)

    def test_authentication_begins_a_fresh_session_after_idle_time_on_lock_screen(self):
        with patch("spm.desktop_interface._session_time", return_value=(10.0, 110.0)) as clock:
            app = DesktopApp(self.root, self.path)
            field = next(child for child in app.view.winfo_children() if isinstance(child, ttk.Entry))
            field.insert(0, self.master)
            button = next(
                child for frame in app.view.winfo_children() if isinstance(frame, ttk.Frame)
                for child in frame.winfo_children()
                if isinstance(child, ttk.Button) and child.cget("text") == "Unlock"
            )
            clock.return_value = (11.0 + LOCK_AFTER, 111.0 + LOCK_AFTER)
            button.invoke()
            self.assertIsNotNone(app.vault)
            app._check_idle()
            self.assertIsNotNone(app.vault)

    def test_lock_removes_revealed_password_and_copy_controls(self):
        entry = Entry("Sample account", "synthetic sample password")
        app = DesktopApp(self.root, self.path)
        app.vault = Vault(self.path, self.master)
        app.vault.add([entry])
        app._show_vault()
        app._refresh(select=entry.name)
        self.root.update()
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
