"""Create, back up, lock, and reopen a disposable vault in the installed app."""

import argparse
import subprocess
import tempfile
from pathlib import Path

from desktop_webdriver import WebDriver, running_driver

MASTER = "Synthetic installed desktop test passphrase"
ACCOUNT = "Installed desktop smoke test"
PASSWORD = "Synthetic entry password 845!"


def click(driver: WebDriver, label: str, selector: str = "button"):
    driver.wait_until(f"enable {label!r}", """
        const [label, selector] = arguments;
        const button = [...document.querySelectorAll(selector)].find(
          item => (item.getAttribute('aria-label') ?? item.textContent).trim() === label
        )?.closest('button');
        if (!button || button.disabled) return false;
        button.click();
        return true;
    """, label, selector)


def fill(driver: WebDriver, selector: str, value: str):
    driver.wait_for(selector)
    driver.execute("""
        const input = document.querySelector(arguments[0]);
        input.value = arguments[1];
        input.dispatchEvent(new Event('input', { bubbles: true }));
    """, selector, value)


def choose_file(title: str, path: Path, *, opening: bool = False):
    window = subprocess.check_output(
        ["xdotool", "search", "--sync", "--onlyvisible", "--name", f"^{title}$"],
        timeout=15, text=True,
    ).splitlines()[0]
    subprocess.run(["xdotool", "windowfocus", "--sync", window], check=True, timeout=5)
    if opening:
        subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+l"], check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], check=True)
    subprocess.run(["xdotool", "type", "--clearmodifiers", str(path)], check=True)
    subprocess.run(["xdotool", "key", "--clearmodifiers", "Return"], check=True)


def unlock(driver: WebDriver):
    fill(driver, "#master-password", MASTER)
    click(driver, "Unlock vault")
    driver.wait_for(".credential-workspace")


def exercise(driver: WebDriver, directory: Path):
    vault = directory / "smoke-vault.spm"
    backup = directory / "smoke-backup.spm"

    driver.wait_for(".vault-file-actions .primary")
    click(driver, "Create vault")
    choose_file("Create a vault", vault)
    fill(driver, "#master-password", MASTER)
    fill(driver, "#confirm-master", MASTER)
    click(driver, "Create vault")
    driver.wait_for(".credential-workspace")
    assert vault.is_file(), "The installed app did not create the selected vault"

    click(driver, "Add entry")
    fill(driver, '[name="name"]', ACCOUNT)
    fill(driver, '[name="username"]', "installed@example.test")
    fill(driver, '.credential-form input[type="password"]', PASSWORD)
    click(driver, "Save credential")
    driver.wait_for(".credential-list", text=ACCOUNT)

    click(driver, "Vault settings")
    driver.wait_for("#vault-files-heading")
    click(driver, "Save backup")
    choose_file("Save encrypted backup", backup)
    driver.wait_for(".feedback", text="Encrypted backup saved.")
    assert backup.is_file(), "The installed app did not create the selected backup"

    click(driver, "Lock vault")
    driver.wait_for("#master-password")
    assert not driver.execute("return Boolean(document.querySelector('.credential-workspace'))")
    unlock(driver)

    click(driver, "Vault settings")
    driver.wait_for("#vault-files-heading")
    click(driver, "Open backup")
    choose_file("Open encrypted backup", backup, opening=True)
    driver.wait_for(".welcome-copy strong", text=backup.name)
    unlock(driver)

    driver.wait_for(".credential-list", text=ACCOUNT)
    click(driver, ACCOUNT, ".credential-row strong")
    driver.wait_for(".detail-content dd", text="installed@example.test")
    driver.wait_for('[aria-label="Reveal password"]')
    click(driver, "Reveal password")
    driver.wait_for(".password-text", text=PASSWORD)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="spm-installed-") as temporary:
        directory = Path(temporary)
        with running_driver(directory / "data") as (driver, _), driver.open(args.executable.resolve(strict=True)):
            exercise(driver, directory)
    print("The installed app created an entry, locked, and reopened the encrypted backup.")


if __name__ == "__main__":
    main()
