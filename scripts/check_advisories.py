"""Apply the release severity threshold to a complete OSV-Scanner JSON report."""

import json
import math
import sys
from pathlib import Path

LOCKFILES = {"uv.lock", "desktop/package-lock.json", "desktop/src-tauri/Cargo.lock"}


def describe(report: dict, root: Path) -> bool:
    """Print one line per advisory group and return whether the severity gate passes."""
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
                if score:
                    number = float(score)
                    if not math.isfinite(number) or not 0 <= number <= 10:
                        raise ValueError(f"Invalid CVSS score for {ids[0]}")
                    blocking |= number >= 7.0
                for identifier in ids:
                    record = advisories[identifier]
                    label = record.get("database_specific", {}).get("severity", "")
                    blocking |= label.upper() in {"HIGH", "CRITICAL"}
                print(f"{path}: {package['name']} {package['version']} | {', '.join(ids)} | {severity}")
            if advisories.keys() != covered:
                raise ValueError(f"Incomplete advisory groups in {path}")
    if sources != LOCKFILES:
        raise ValueError(f"Unexpected scan coverage: {sorted(sources)}")
    return not blocking


if __name__ == "__main__":
    try:
        passed = describe(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), Path.cwd())
    except (KeyError, ValueError, TypeError, OSError) as error:
        sys.exit(f"Could not verify the advisory report: {error}")
    if not passed:
        sys.exit("Resolve high and critical advisories before release.")
