"""Measure a Linux Tauri build against a disposable synthetic vault."""

import argparse
import json
import os
import platform
import socket
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from spm.adapters.spm_codec import _derive_key
from spm.vault import Entry, Vault

MASTER = "Synthetic performance test passphrase"
ENTRY_COUNT = 10_000
SEARCH = """
const done = arguments[arguments.length - 1];
const input = document.querySelector('.search-box input');
const start = performance.now();
input.value = arguments[0];
input.dispatchEvent(new Event('input', { bubbles: true }));
requestAnimationFrame(() => requestAnimationFrame(() => {
  done({
    elapsed: performance.now() - start,
    first: document.querySelector('.entries li strong')?.textContent,
    rows: document.querySelectorAll('.entries li').length,
  });
}));
"""


class WebDriver:
    def __init__(self, port: int):
        self.address = f"http://127.0.0.1:{port}"
        self.session = ""

    def request(self, method: str, path: str, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(
            self.address + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)["value"]
        except HTTPError as error:
            failure = json.load(error)["value"]
            raise RuntimeError(f"WebDriver {method} {path}: {failure['message']}") from error

    def command(self, path: str, payload):
        return self.request("POST", f"/session/{self.session}/{path}", payload)

    def execute(self, script: str, *args, asynchronous=False):
        return self.command("execute/async" if asynchronous else "execute/sync", {
            "script": script, "args": list(args),
        })

    def wait_for(self, selector: str):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.execute("return Boolean(document.querySelector(arguments[0]))", selector):
                return
            time.sleep(0.02)
        raise RuntimeError(f"Desktop did not render {selector}")


def process_tree(pid: int):
    yield pid
    children_file = Path(f"/proc/{pid}/task/{pid}/children")
    for child in children_file.read_text().split():
        yield from process_tree(int(child))


def desktop_memory(driver_pid: int, executable: Path) -> float:
    for pid in process_tree(driver_pid):
        try:
            if Path(f"/proc/{pid}/exe").resolve(strict=True) == executable:
                return sum(process_pss(child) for child in process_tree(pid)) / 1024
        except FileNotFoundError:
            continue
    raise RuntimeError("Could not find the desktop process in the WebDriver process tree")


def process_pss(pid: int) -> int:
    for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
        if line.startswith("Pss:"):
            return int(line.split()[1])
    raise RuntimeError(f"Missing PSS for process {pid}")


def prepare(data_home: Path) -> int:
    vault = data_home / "SecurePasswordManager" / "vault.spm"
    Vault.create(vault, MASTER)
    Vault(vault, MASTER).add(
        Entry(f"Account {i:05d}", f"Synthetic account password {i}",
              f"user-{i}@example.test", f"https://example.test/site-{i:05d}")
        for i in range(ENTRY_COUNT)
    )
    return vault.stat().st_size


def measure(driver: WebDriver, executable: Path, driver_pid: int):
    start = time.perf_counter()
    response = driver.request("POST", "/session", {
        "capabilities": {"alwaysMatch": {
            "webkitgtk:browserOptions": {"binary": str(executable), "args": []},
        }},
    })
    driver.session = response["sessionId"]
    try:
        driver.wait_for("#master-password")
        startup_ms = (time.perf_counter() - start) * 1000
        driver.execute("""
            const input = document.querySelector('#master-password');
            input.value = arguments[0];
            input.form.requestSubmit();
        """, MASTER)
        driver.wait_for(".search-box input")
        if driver.execute("return document.querySelectorAll('.entries li').length") != 100:
            raise RuntimeError("The synthetic vault did not render its first page")
        desktop_pss_mib = desktop_memory(driver_pid, executable)
        searches = []
        for i in range(10):
            account = (i * 997 + 10) % ENTRY_COUNT
            result = driver.execute(SEARCH, f"site-{account:05d}", asynchronous=True)
            if result["first"] != f"Account {account:05d}" or result["rows"] != 1:
                raise RuntimeError("The desktop search returned unexpected results")
            searches.append(result["elapsed"])
        return startup_ms, desktop_pss_mib, searches
    finally:
        driver.request("DELETE", f"/session/{driver.session}")


def wait_for_driver(driver: WebDriver, process: subprocess.Popen):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and process.poll() is None:
        try:
            if driver.request("GET", "/status")["ready"]:
                return
        except URLError:
            time.sleep(0.05)
    raise RuntimeError("WebKitWebDriver did not start")


def benchmark(executable: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="spm-performance-") as directory:
        data_home = Path(directory)
        vault_bytes = prepare(data_home)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        driver = WebDriver(port)
        env = os.environ | {"XDG_DATA_HOME": directory, "TAURI_WEBVIEW_AUTOMATION": "true"}
        command = ["WebKitWebDriver", "--host=127.0.0.1", f"--port={port}"]
        with subprocess.Popen(command, env=env) as process:
            try:
                wait_for_driver(driver, process)
                runs = [measure(driver, executable, process.pid) for _ in range(3)]
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

    argon2_ms = []
    for _ in range(5):
        start = time.perf_counter()
        _derive_key(MASTER, bytes(16))
        argon2_ms.append((time.perf_counter() - start) * 1000)
    startup_ms, desktop_pss_mib, searches = zip(*runs)
    return {
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "webkitgtk": subprocess.check_output(
                ["pkg-config", "--modversion", "webkit2gtk-4.1"], text=True,
            ).strip(),
            "commit": os.environ.get("GITHUB_SHA") or subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True,
            ).strip(),
            "cpu_model": next((
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ), "unknown"),
        },
        "vault": {"entries": ENTRY_COUNT, "bytes": vault_bytes},
        "startup_to_unlock_ui_ms": samples(startup_ms),
        "search_input_to_render_ms": samples([sample for run in searches for sample in run]),
        "unlocked_desktop_pss_mib": samples(desktop_pss_mib),
        "argon2id_ms": samples(argon2_ms),
    }


def samples(values) -> dict:
    return {"median": round(statistics.median(values), 2),
            "max": round(max(values), 2), "count": len(values)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.dumps(benchmark(args.executable.resolve(strict=True)), indent=2)
    args.report.write_text(report + "\n", encoding="utf-8")
    print(report)
