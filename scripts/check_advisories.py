"""Apply the release severity threshold to a complete OSV-Scanner JSON report."""

import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LOCKFILES = {"uv.lock", "desktop/package-lock.json", "desktop/src-tauri/Cargo.lock"}
EXCEPTIONS = Path(__file__).with_name("advisory-exceptions.json")
EXCEPTION_FIELDS = {"id", "package", "version", "lockfile", "reason", "expires"}
MAX_EXCEPTION_DAYS = 90


def load_exceptions(entries: list, today: date) -> dict:
    """Validate accepted-risk entries and index them by (lockfile, package, version, id)."""
    if not isinstance(entries, list):
        raise ValueError("Advisory exceptions must be a list")
    index = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != EXCEPTION_FIELDS:
            fields = sorted(EXCEPTION_FIELDS)
            raise ValueError(f"Advisory exceptions need exactly these fields: {fields}")
        if not all(isinstance(entry[key], str) and entry[key].strip() for key in EXCEPTION_FIELDS):
            raise ValueError(f"Empty field in the advisory exception for {entry['id']}")
        if entry["lockfile"] not in LOCKFILES:
            raise ValueError(f"Unknown lockfile in the advisory exception for {entry['id']}")
        expires = date.fromisoformat(entry["expires"])
        if expires > today + timedelta(days=MAX_EXCEPTION_DAYS):
            raise ValueError(
                f"The exception for {entry['id']} must expire within {MAX_EXCEPTION_DAYS} days")
        key = (entry["lockfile"], entry["package"], entry["version"], entry["id"])
        if key in index:
            raise ValueError(f"Duplicate advisory exception for {entry['id']}")
        index[key] = {**entry, "expires": expires}
    return index


def apply_exceptions(blocks: bool, keys: list, exceptions: dict, today: date) -> tuple[bool, str]:
    """Return whether a group still blocks and a note, given its advisory keys."""
    matched = [exceptions[key] for key in keys if key in exceptions]
    if not blocks or len(matched) != len(keys):
        return blocks, ""
    expiry = min(entry["expires"] for entry in matched)
    if expiry < today:
        return True, f" | exception expired on {expiry.isoformat()}"
    return False, f" | accepted until {expiry.isoformat()}"


def describe(report: dict, root: Path, exceptions: dict | None = None,
             today: date | None = None) -> bool:
    """Print one line per advisory group and return whether the severity gate passes.

    A blocking group passes only when every advisory in it has an unexpired
    exception for the same lockfile, package, and version. Expired and unused
    exceptions fail the gate so accepted risks are revisited.
    """
    exceptions = exceptions or {}
    today = today or datetime.now(timezone.utc).date()
    used = set()
    sources = set()
    blocking = False
    for result in report["results"]:
        path = Path(result["source"]["path"]).resolve().relative_to(root).as_posix()
        if result["source"]["type"] != "lockfile" or path in sources or not result["packages"]:
            raise ValueError(f"Invalid or empty lockfile result for {path}")
        sources.add(path)
        for item in result["packages"]:
            package = item["package"]
            advisories = {entry["id"]: entry for entry in item.get("vulnerabilities", [])}
            covered = set()
            for group in item.get("groups", []):
                ids = group["ids"]
                if not ids:
                    raise ValueError("Empty advisory group")
                covered.update(ids)
                score = group.get("max_severity")
                severity = "unknown" if not score else f"CVSS {score}"
                group_blocks = False
                if score:
                    number = float(score)
                    if not math.isfinite(number) or not 0 <= number <= 10:
                        raise ValueError(f"Invalid CVSS score for {ids[0]}")
                    group_blocks |= number >= 7.0
                for identifier in ids:
                    record = advisories[identifier]
                    label = record.get("database_specific", {}).get("severity", "")
                    group_blocks |= label.upper() in {"HIGH", "CRITICAL"}
                keys = [(path, package["name"], package["version"], advisory) for advisory in ids]
                used.update(key for key in keys if key in exceptions)
                group_blocks, note = apply_exceptions(group_blocks, keys, exceptions, today)
                blocking |= group_blocks
                print(f"{path}: {package['name']} {package['version']} | {', '.join(ids)} | "
                      f"{severity}{note}")
            if advisories.keys() != covered:
                raise ValueError(f"Incomplete advisory groups in {path}")
    if sources != LOCKFILES:
        raise ValueError(f"Unexpected scan coverage: {sorted(sources)}")
    for key in sorted(exceptions.keys() - used):
        lockfile, name, version, identifier = key
        print(f"Remove the unused advisory exception for {identifier} "
              f"({name} {version} in {lockfile}).")
        blocking = True
    return not blocking


if __name__ == "__main__":
    try:
        current = datetime.now(timezone.utc).date()
        accepted = load_exceptions(json.loads(EXCEPTIONS.read_text(encoding="utf-8")), current)
        report_data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        passed = describe(report_data, Path.cwd(), accepted, current)
    except (KeyError, ValueError, TypeError, OSError) as error:
        sys.exit(f"Could not verify the advisory report: {error}")
    if not passed:
        sys.exit("Resolve high and critical advisories before release.")
