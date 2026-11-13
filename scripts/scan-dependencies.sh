#!/usr/bin/env bash
set -euo pipefail

report=${1:?Supply a path for the OSV JSON report}
scanner=${OSV_SCANNER:-osv-scanner}
temporary=$(mktemp "${report}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT

status=0
"$scanner" scan source --lockfile=uv.lock --lockfile=desktop/package-lock.json \
  --lockfile=desktop/src-tauri/Cargo.lock --all-vulns --all-packages \
  --format=json --output-file="$temporary" || status=$?
if [[ $status != 0 && $status != 1 ]]; then
  exit "$status"
fi
mv -- "$temporary" "$report"
python3 scripts/check_advisories.py "$report"
