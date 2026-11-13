"""Exercise the desktop process through its real pipe entry point."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from spm.vault_protocol import MAX_REQUEST_BYTES

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

    def test_oversized_frame_ends_the_session(self):
        result, replies = self.run_process(b"x" * MAX_REQUEST_BYTES + b"\n" + frame(2, "list"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(replies), 1)
        self.assertIsNone(replies[0]["id"])
        self.assertEqual(replies[0]["error"]["code"], "request_too_large")
