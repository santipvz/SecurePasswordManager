"""Tests for the dependency advisory gate and its accepted-risk exceptions."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_advisories  # noqa: E402  pylint: disable=wrong-import-position

TODAY = date(2026, 11, 17)
NPM = "desktop/package-lock.json"


def exception(**changes) -> dict:
    entry = {
        "id": "GHSA-test-0001", "package": "picomatch", "version": "4.0.7", "lockfile": NPM,
        "reason": "Build-time only.", "expires": "2027-01-17",
    }
    return {**entry, **changes}


class AdvisoryGateTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()

    def report(self, *, score="8.7", ids=("GHSA-test-0001",), version="4.0.7", severity="") -> dict:
        def result(lockfile, packages):
            return {"source": {"path": str(self.root / lockfile), "type": "lockfile"}, "packages": packages}

        clean = {"package": {"name": "clean", "version": "1.0.0"}}
        flagged = {
            "package": {"name": "picomatch", "version": version},
            "vulnerabilities": [{"id": i, "database_specific": {"severity": severity}} for i in ids],
            "groups": [{"ids": list(ids), "max_severity": score}],
        }
        return {"results": [
            result("uv.lock", [clean]),
            result(NPM, [clean, flagged]),
            result("desktop/src-tauri/Cargo.lock", [clean]),
        ]}

    def gate(self, report, entries=(), today=TODAY) -> bool:
        accepted = check_advisories.load_exceptions(list(entries), today)
        with contextlib.redirect_stdout(io.StringIO()):
            return check_advisories.describe(report, self.root, accepted, today)

    def test_high_advisory_without_exception_blocks(self):
        self.assertFalse(self.gate(self.report()))

    def test_medium_advisory_passes(self):
        self.assertTrue(self.gate(self.report(score="6.9")))

    def test_high_severity_label_blocks_unscored_advisory(self):
        self.assertFalse(self.gate(self.report(score="", severity="HIGH")))

    def test_matching_exception_accepts_the_group(self):
        self.assertTrue(self.gate(self.report(), [exception()]))

    def test_expired_exception_blocks(self):
        self.assertFalse(self.gate(self.report(), [exception(expires="2026-11-16")]))

    def test_expired_exception_blocks_after_a_severity_downgrade(self):
        self.assertFalse(self.gate(self.report(score="6.9"), [exception(expires="2026-11-16")]))

    def test_exception_is_valid_on_its_expiry_date(self):
        self.assertTrue(self.gate(self.report(), [exception(expires="2026-11-17")]))

    def test_exception_for_another_version_does_not_apply(self):
        self.assertFalse(self.gate(self.report(version="4.0.8"), [exception()]))

    def test_every_advisory_in_a_group_needs_an_exception(self):
        report = self.report(ids=("GHSA-test-0001", "GHSA-test-0002"))
        self.assertFalse(self.gate(report, [exception()]))

    def test_unused_exception_blocks(self):
        self.assertFalse(self.gate(self.report(score="6.9", ids=("GHSA-other",)), [exception()]))

    def test_exception_must_expire_within_ninety_days(self):
        with self.assertRaises(ValueError):
            check_advisories.load_exceptions([exception(expires="2027-03-01")], TODAY)

    def test_exception_requires_every_field(self):
        entry = exception()
        del entry["reason"]
        with self.assertRaises(ValueError):
            check_advisories.load_exceptions([entry], TODAY)

    def test_exception_rejects_unknown_lockfile(self):
        with self.assertRaises(ValueError):
            check_advisories.load_exceptions([exception(lockfile="package-lock.json")], TODAY)

    def test_duplicate_exceptions_are_rejected(self):
        with self.assertRaises(ValueError):
            check_advisories.load_exceptions([exception(), exception()], TODAY)

    def test_repository_exceptions_are_well_formed(self):
        entries = json.loads(check_advisories.EXCEPTIONS.read_text(encoding="utf-8"))
        for entry in entries:
            # Check the structure as of the entry's own expiry, independent of the clock.
            check_advisories.load_exceptions([entry], date.fromisoformat(entry["expires"]))

if __name__ == "__main__":
    unittest.main()
