"""Start and control WebKitWebDriver for Linux desktop checks."""

import json
import os
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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

    @contextmanager
    def open(self, executable: Path):
        response = self.request("POST", "/session", {
            "capabilities": {"alwaysMatch": {
                "webkitgtk:browserOptions": {"binary": str(executable), "args": []},
            }},
        })
        self.session = response["sessionId"]
        try:
            yield self
        finally:
            self.request("DELETE", f"/session/{self.session}")

    def wait_for(self, selector: str, *, text: str | None = None):
        expectation = selector if text is None else f"{selector} containing {text!r}"
        self.wait_until(f"render {expectation}", """
            const [selector, text] = arguments;
            const item = document.querySelector(selector);
            return Boolean(item && (text === null || item.textContent.includes(text)));
        """, selector, text)

    def wait_until(self, expectation: str, script: str, *args):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.execute(script, *args):
                return
            time.sleep(0.02)
        raise RuntimeError(f"Desktop did not {expectation}")


def wait_for_driver(driver: WebDriver, process: subprocess.Popen):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and process.poll() is None:
        try:
            if driver.request("GET", "/status")["ready"]:
                return
        except URLError:
            time.sleep(0.05)
    raise RuntimeError("WebKitWebDriver did not start")


@contextmanager
def running_driver(data_home: Path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    driver = WebDriver(port)
    env = os.environ | {"XDG_DATA_HOME": str(data_home), "TAURI_WEBVIEW_AUTOMATION": "true"}
    command = ["WebKitWebDriver", "--host=127.0.0.1", f"--port={port}"]
    with subprocess.Popen(command, env=env) as process:
        try:
            wait_for_driver(driver, process)
            yield driver, process.pid
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
