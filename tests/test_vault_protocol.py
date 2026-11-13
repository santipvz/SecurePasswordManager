"""Exercise the desktop process through its real pipe entry point."""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic, sleep
from unittest.mock import Mock, patch

from spm.security_key import SecurityKeyError
from spm.vault_protocol import MAX_REQUEST_BYTES, serve

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MASTER = "Synthetic compatibility passphrase"


def frame(request_id, operation, **fields):
    return json.dumps({"version": 1, "id": request_id, "operation": operation, **fields}).encode() + b"\n"


class VaultProtocolTests(unittest.TestCase):
    def run_process(self, source):
        result = subprocess.run(
            [sys.executable, "-m", "spm.vault_protocol"], input=source,
            capture_output=True, check=False, timeout=10,
        )
        self.assertEqual(result.stderr, b"")
        return result, [json.loads(line) for line in result.stdout.splitlines()]

    def test_open_list_and_lock_both_existing_formats(self):
        for filename, has_key in (("password-v1.spm", False), ("fido2-v2.spm", True)):
            with self.subTest(filename=filename):
                path = str(FIXTURES / filename)
                result, replies = self.run_process(b"".join([
                    frame(1, "list"), frame(2, "status", path=path),
                    frame(3, "open", path=path, master=MASTER),
                    frame(4, "list", query="fixture"), frame(5, "lock"), frame(6, "list"),
                ]))
                self.assertEqual(result.returncode, 0)
                self.assertEqual([reply["id"] for reply in replies], list(range(1, 7)))
                self.assertEqual(replies[0]["error"]["code"], "locked")
                self.assertEqual(replies[1]["result"], {
                    "exists": True, "unlocked": False, "has_security_key": has_key,
                })
                self.assertEqual(replies[2]["result"], {"unlocked": True, "has_security_key": has_key})
                self.assertEqual(replies[3]["result"], {"entries": [{
                    "name": "Fixture account", "username": "fixture@example.test",
                    "url": "https://example.test",
                }]})
                self.assertEqual(replies[4]["result"], {"unlocked": False})
                self.assertEqual(replies[5]["error"]["code"], "locked")
                self.assertNotIn(MASTER.encode(), result.stdout)
                self.assertNotIn(b"synthetic password only", result.stdout)
                self.assertNotIn(b"Synthetic data only.", result.stdout)

    def test_invalid_frames_and_failed_open_keep_sensitive_data_out_of_replies(self):
        path = str(FIXTURES / "password-v1.spm")
        result, replies = self.run_process(b"".join([
            b'{"id":2,"id":3}\n', b'["bad frame"]\n', b"\xff\n",
            frame(4, "lock", version=2), frame(5, "list", query=[]),
            frame(6, "open", path=path, master=MASTER),
            frame(7, "open", path=path, master="wrong password"), frame(8, "list"),
        ]))
        self.assertEqual(result.returncode, 0)
        self.assertEqual([reply.get("error", {}).get("code") for reply in replies], [
            "invalid_request", "invalid_request", "invalid_request", "unsupported_version",
            "invalid_request", None, "open_failed", "locked",
        ])
        self.assertNotIn(b"wrong password", result.stdout)

    def test_creates_a_vault_without_overwriting_files(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "new.spm"
            result, replies = self.run_process(b"".join([
                frame(1, "create", path=str(path), master="too short"),
                frame(2, "status", path=str(path)),
                frame(3, "create", path=str(path), master=MASTER),
                frame(4, "list"), frame(5, "lock"),
            ]))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(replies[0]["error"]["code"], "weak_master")
            self.assertFalse(replies[1]["result"]["exists"])
            self.assertEqual(replies[2]["result"], {"unlocked": True, "has_security_key": False})
            self.assertEqual(replies[3]["result"], {"entries": []})
            original = path.read_bytes()
            self.assertTrue(original.startswith(b"SPM\x01"))
            self.assertNotIn(MASTER.encode(), original)

            _, replies = self.run_process(
                frame(6, "create", path=str(path), master="A different master password")
                + frame(7, "open", path=str(path), master=MASTER)
            )
            self.assertEqual(replies[0]["error"]["code"], "create_failed")
            self.assertTrue(replies[1]["result"]["unlocked"])
            self.assertEqual(path.read_bytes(), original)

    @unittest.skipIf(os.name == "nt", "Creating symlinks may require Windows privileges")
    def test_create_does_not_follow_a_dangling_destination_symlink(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "target.spm"
            selected = Path(directory) / "selected.spm"
            selected.symlink_to(target)
            _, replies = self.run_process(frame(1, "create", path=str(selected), master=MASTER))
            self.assertEqual(replies[0]["error"]["code"], "create_failed")
            self.assertTrue(selected.is_symlink())
            self.assertFalse(target.exists())

    def test_fido2_unlock_failures_and_compatibility(self):
        fixture = FIXTURES / "fido2-v2.spm"
        with TemporaryDirectory() as directory:
            tampered = Path(directory) / "tampered.spm"
            original = fixture.read_bytes()
            tampered.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            for error, prf, path, code in (
                (None, b"T" * 32, fixture, None),
                (None, b"!" * 32, fixture, "key_failed"),
                (None, b"T" * 32, tampered, "key_failed"),
                ("key_disconnected", None, fixture, "key_disconnected"),
                ("wrong_key", None, fixture, "wrong_key"),
                ("pin_invalid", None, fixture, "pin_invalid"),
            ):
                with self.subTest(code=code, path=path.name):
                    before = path.read_bytes()
                    device = Mock()
                    device.derive.return_value = prf
                    started, finished = Event(), Event()

                    @contextmanager
                    def key(read_pin, _notify, *, cancel, window):
                        self.assertIsNone(window)
                        self.assertEqual(read_pin(), None if os.name == "nt" else "fake-pin")
                        started.set()
                        if error:
                            raise SecurityKeyError(error, "sensitive adapter details")
                        self.assertFalse(cancel.is_set())
                        yield device
                        finished.set()

                    fields = {} if os.name == "nt" else {"pin": "fake-pin"}
                    with patch("spm.vault_protocol.open_security_key", key):
                        replies = self.exchange_key(frame(1, "open_key", path=str(path), **fields))
                    self.assertTrue(started.is_set())
                    if code:
                        self.assertEqual(replies[0]["error"]["code"], code)
                        self.assertEqual(replies[1]["error"]["code"], "locked")
                    else:
                        self.assertTrue(finished.is_set())
                        self.assertEqual(replies[0]["result"], {"unlocked": True, "has_security_key": True})
                        self.assertEqual(replies[1]["result"]["entries"][0]["name"], "Fixture account")
                        device.derive.assert_called_once_with(b"synthetic credential", bytes(range(32)))
                    self.assertNotIn("fake-pin", str(replies))
                    self.assertNotIn("sensitive adapter details", str(replies))
                    self.assertEqual(path.read_bytes(), before)

    def exchange_key(self, request, started=None):
        read, write = os.pipe()
        output = io.BytesIO()
        with os.fdopen(read, "rb") as source, os.fdopen(write, "wb") as client:
            worker = Thread(target=serve, args=(source, output), daemon=True)
            worker.start()
            client.write(request)
            client.flush()
            if started:
                self.assertTrue(started.wait(5))
            else:
                # Keep the connection open through the authenticator request.
                deadline = monotonic() + 5
                while b"\n" not in output.getvalue() and monotonic() < deadline:
                    sleep(0.01)
                self.assertIn(b"\n", output.getvalue())
                client.write(frame(2, "list"))
                client.flush()
            client.close()
            worker.join(5)
            self.assertFalse(worker.is_alive())
        return [json.loads(line) for line in output.getvalue().splitlines()]

    def test_disconnect_cancels_the_key_and_rejects_late_success(self):
        started = Event()
        device = Mock()
        device.derive.return_value = b"T" * 32

        @contextmanager
        def key(_read_pin, _notify, *, cancel, window):
            self.assertIsNone(window)
            started.set()
            self.assertTrue(cancel.wait(5))
            yield device

        with patch("spm.vault_protocol.open_security_key", key):
            replies = self.exchange_key(
                frame(1, "open_key", path=str(FIXTURES / "fido2-v2.spm")), started,
            )
        self.assertEqual(replies[0]["error"]["code"], "key_interrupted")
        device.derive.assert_called_once()

    def test_oversized_frame_ends_the_session(self):
        result, replies = self.run_process(b"x" * MAX_REQUEST_BYTES + b"\n" + frame(2, "list"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(replies), 1)
        self.assertIsNone(replies[0]["id"])
        self.assertEqual(replies[0]["error"]["code"], "request_too_large")
