"""Build the private vault process for the current platform."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main() -> None:
    scripts = Path(__file__).resolve().parent
    resources = scripts.parent / "src-tauri" / "resources"
    target = resources / "vault-process"
    name = "cpass-vault-process"
    executable = f"{name}.exe" if os.name == "nt" else name
    resources.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=resources) as workspace:
        work = Path(workspace)
        subprocess.run(
            [
                sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir",
                "--collect-data", "fido2",
                "--name", name, "--distpath", str(work / "dist"),
                "--workpath", str(work / "build"), "--specpath", str(work),
                str(scripts / "vault_process_entry.py"),
            ],
            check=True,
        )
        bundle = work / "dist" / name
        if not (bundle / executable).is_file():
            raise RuntimeError("Vault process executable is missing from the bundle")
        if target.exists():
            shutil.rmtree(target)
        bundle.rename(target)


if __name__ == "__main__":
    main()
