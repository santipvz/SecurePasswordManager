"""Collect license notices for the Ubuntu desktop package."""

from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
import sysconfig
import tempfile


NOTICE_PREFIXES = ("license", "licence", "copying", "copyright", "notice", "unlicense")


def copy_notice(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def copy_rust_notices(tauri: Path, destination: Path) -> None:
    result = subprocess.run(
        ["cargo", "metadata", "--locked", "--format-version", "1",
         "--filter-platform", "x86_64-unknown-linux-gnu"],
        cwd=tauri,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    cargo = json.loads(result.stdout)
    for package in cargo["packages"]:
        if package["id"] == cargo["resolve"]["root"]:
            continue
        directory = Path(package["manifest_path"]).parent
        target = destination / f"{package['name']}-{package['version']}"
        for path in directory.iterdir():
            if path.is_file() and path.name.lower().startswith(NOTICE_PREFIXES):
                copy_notice(path, target / path.name)
        if package["license_file"]:
            path = directory / package["license_file"]
            copy_notice(path, target / path.name)


def copy_python_notices(destination: Path) -> None:
    copy_notice(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", destination / "CPython.txt")
    for distribution in metadata.distributions():
        for path in distribution.files or ():
            if any(part.endswith(".dist-info") for part in path.parts) and (
                "licenses" in path.parts or path.name.lower().startswith(NOTICE_PREFIXES)
            ):
                copy_notice(path.locate(), destination / path)


def main() -> None:
    desktop = Path(__file__).resolve().parents[1]
    tauri = desktop / "src-tauri"
    resources = tauri / "resources"
    resources.mkdir(parents=True, exist_ok=True)
    destination = resources / "notices"
    with tempfile.TemporaryDirectory(dir=resources) as workspace:
        staged = Path(workspace) / "notices"
        copy_notice(desktop / "dist" / "frontend-licenses.md", staged / "frontend.md")
        copy_rust_notices(tauri, staged / "rust")
        copy_python_notices(staged / "python")
        if destination.exists():
            shutil.rmtree(destination)
        staged.rename(destination)


if __name__ == "__main__":
    main()
