"""A bounded request and response protocol for the bundled desktop process."""

import json
import re
import stat
import sys
from dataclasses import asdict
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from typing import BinaryIO

from .domain.review import MIN_REVIEW_LENGTH, review_credentials
from .sec_pass_manager import MAX_LENGTH, MIN_LENGTH, generate_password
from .security_key import SecurityKeyError, open_security_key
from .vault import (
    MIN_MASTER_LENGTH, Entry, Vault, VaultConflict, VaultError, default_vault_path,
    vault_has_security_key,
)

VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
MAX_REQUEST_ID = (1 << 53) - 1
OPERATIONS = {
    "status": {"path"},
    "open": {"path", "master"},
    "open_key": {"path", "pin", "window"},
    "create": {"path", "master"},
    "list": {"query"},
    "generate": {"length", "symbols"},
    "review": set(),
    "entry_notes": {"name"},
    "entry_password": {"name"},
    "save_entry": {"previous", "name", "password", "username", "url", "notes"},
    "delete_entry": {"name"},
    "lock": set(),
}
REQUIRED_FIELDS = {"version", "id", "operation"}
OPERATION_REQUIRED_FIELDS = {
    "open": {"master"},
    "generate": {"length", "symbols"},
    "create": {"path", "master"},
    "entry_notes": {"name"},
    "entry_password": {"name"},
    "save_entry": {"name"},
    "delete_entry": {"name"},
}
ERROR_MESSAGES = {
    "invalid_request": "Invalid request.",
    "request_too_large": "Request exceeds 64 KiB.",
    "unsupported_version": "Unsupported protocol version.",
    "unknown_operation": "Unknown operation.",
    "locked": "Unlock the vault first.",
    "open_failed": "Could not unlock the vault. Check the password and file.",
    "file_error": "The vault file could not be accessed.",
    "create_failed": "Could not create a vault. Choose a new file in a writable folder.",
    "weak_master": f"Use at least {MIN_MASTER_LENGTH} characters for the master password.",
    "key_disconnected": "Connect a FIDO2 key and check its permissions.",
    "key_failed": "Could not unlock with this key. Check the vault or use the master password.",
    "key_interrupted": "The FIDO2 operation timed out or was cancelled.",
    "key_setup_required": "Set up a FIDO2 PIN on the key.",
    "key_unsupported": "The key or system does not support the required FIDO2 features.",
    "multiple_keys": "Connect only the FIDO2 key you want to use.",
    "pin_blocked": "The PIN is blocked. Reconnect the key or use the master password.",
    "pin_invalid": "The FIDO2 PIN is incorrect.",
    "pin_required": "Enter the FIDO2 key PIN.",
    "wrong_key": "The connected key has no credential for this vault.",
    "generator_length": f"Choose a length from {MIN_LENGTH} to {MAX_LENGTH} characters.",
    "entry_missing": "The credential no longer exists.",
    "entry_duplicate": "A credential with that name already exists.",
    "entry_invalid": "Enter a name and password for the credential.",
    "write_conflict": "The vault changed on disk. Lock and reopen it before making changes.",
    "write_failed": "Could not confirm the vault was saved. Check the file and reopen the vault.",
}


class ProtocolError(Exception):
    """An error with a stable public code and message."""

    def __init__(self, code: str):
        super().__init__(ERROR_MESSAGES[code])
        self.code = code


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _request_id(value) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_REQUEST_ID:
        return value
    return None


def _validate(request: dict) -> str:
    if not REQUIRED_FIELDS <= request.keys() or _request_id(request["id"]) is None:
        raise ProtocolError("invalid_request")
    version = request["version"]
    if not isinstance(version, int) or isinstance(version, bool) or version != VERSION:
        raise ProtocolError("unsupported_version")
    operation = request["operation"]
    if not isinstance(operation, str):
        raise ProtocolError("invalid_request")
    if operation not in OPERATIONS:
        raise ProtocolError("unknown_operation")
    if request.keys() - REQUIRED_FIELDS - OPERATIONS[operation]:
        raise ProtocolError("invalid_request")
    fields = OPERATIONS[operation] & request.keys()
    if operation == "generate":
        length = request.get("length")
        if (
            not isinstance(length, int)
            or isinstance(length, bool)
            or not isinstance(request.get("symbols"), bool)
        ):
            raise ProtocolError("invalid_request")
    elif not all(isinstance(request[field], str) for field in fields):
        raise ProtocolError("invalid_request")
    if not OPERATION_REQUIRED_FIELDS.get(operation, set()) <= request.keys():
        raise ProtocolError("invalid_request")
    if "window" in request and (
        sys.platform != "win32" or not re.fullmatch(r"[1-9a-f][0-9a-f]{0,15}", request["window"])
    ):
        raise ProtocolError("invalid_request")
    if sys.platform == "win32" and request.get("pin"):
        raise ProtocolError("invalid_request")
    if "path" in request and (not request["path"] or "\0" in request["path"]):
        raise ProtocolError("invalid_request")
    return operation


class _Session:
    def __init__(self, closed: Event):
        self._vault: Vault | None = None
        self._closed = closed

    def execute(self, operation: str, request: dict) -> dict:
        """Run a validated operation against this connection's vault session."""
        match operation:
            case "status":
                return self._status(request)
            case "open" | "open_key" | "create":
                return self._open(operation, request)
            case "generate":
                return _generate(request)
            case "lock":
                self._vault = None
                return {"unlocked": False}
            case _:
                if self._vault is None:
                    raise ProtocolError("locked")
                return _credential_request(self._vault, operation, request)

    def _open(self, operation: str, request: dict) -> dict:
        self._vault = None
        path = _path(request, for_create=operation == "create")
        if operation == "create":
            self._create(path, request["master"])
        elif operation == "open_key":
            self._open_key(path, request)
        else:
            try:
                _regular_file(path)
                self._vault = Vault(path, request["master"])
            except (OSError, VaultError, ValueError) as error:
                raise ProtocolError("open_failed") from error
        return {"unlocked": True, "has_security_key": self._vault.has_security_key}

    def _create(self, path: Path, master: str) -> None:
        if len(master) < MIN_MASTER_LENGTH or not master.strip():
            raise ProtocolError("weak_master")
        try:
            Vault.create(path, master)
            self._vault = Vault(path, master)
        except (OSError, VaultError, ValueError) as error:
            raise ProtocolError("create_failed") from error

    def _open_key(self, path: Path, request: dict) -> None:
        if self._closed.is_set():
            raise ProtocolError("key_interrupted")
        try:
            _regular_file(path)
            if not vault_has_security_key(path):
                raise ProtocolError("key_failed")
            window = int(request["window"], 16) if "window" in request else None
            with open_security_key(
                lambda: request.get("pin"), lambda _message: None,
                cancel=self._closed, window=window,
            ) as key:
                vault = Vault(path, security_key=key)
            if self._closed.is_set():
                raise ProtocolError("key_interrupted")
            self._vault = vault
        except SecurityKeyError as error:
            code = error.code if error.code in ERROR_MESSAGES else "key_failed"
            raise ProtocolError(code) from error
        except (OSError, VaultError, ValueError) as error:
            raise ProtocolError("key_failed") from error

    def _status(self, request: dict) -> dict:
        path = _path(request)
        try:
            _regular_file(path)
            exists = True
        except FileNotFoundError:
            exists = False
        except (OSError, ValueError) as error:
            raise ProtocolError("file_error") from error
        unlocked = self._vault is not None and self._vault.path == path
        return {
            "exists": exists,
            "unlocked": unlocked,
            "has_security_key": exists and vault_has_security_key(path),
        }


def _generate(request: dict) -> dict:
    try:
        return {"password": generate_password(request["length"], symbols=request["symbols"])}
    except ValueError as error:
        raise ProtocolError("generator_length") from error


def _metadata(entry: Entry) -> dict:
    return {"name": entry.name, "username": entry.username, "url": entry.url}


def _entry(vault: Vault, name: str) -> Entry:
    try:
        return vault.get(name)
    except VaultError as error:
        raise ProtocolError("entry_missing") from error


def _save_entry(vault: Vault, request: dict) -> dict:
    previous = _entry(vault, request["previous"]) if "previous" in request else None
    password = request.get("password", previous.password if previous else "")
    try:
        entry = Entry(
            name=request["name"], password=password, username=request.get("username", ""),
            url=request.get("url", ""), notes=request.get("notes", ""),
        )
    except VaultError as error:
        raise ProtocolError("entry_invalid") from error

    if previous is None or previous.name.casefold() != entry.name.casefold():
        try:
            vault.get(entry.name)
        except VaultError:
            pass  # An unused name can be added or used for the rename.
        else:
            raise ProtocolError("entry_duplicate")
    if previous is None:
        vault.add([entry])
    else:
        vault.edit(previous.name, entry)
    return _metadata(entry)


def _credential_request(vault: Vault, operation: str, request: dict) -> dict:
    try:
        match operation:
            case "list":
                entries = vault.list(request.get("query", ""))
                return {"entries": [_metadata(entry) for entry in entries]}
            case "review":
                findings = review_credentials(vault.list())
                return {**asdict(findings), "minimum_length": MIN_REVIEW_LENGTH}
            case "entry_notes":
                return {"notes": _entry(vault, request["name"]).notes}
            case "entry_password":
                return {"password": _entry(vault, request["name"]).password}
            case "save_entry":
                return _save_entry(vault, request)
            case "delete_entry":
                entry = _entry(vault, request["name"])
                vault.delete(entry.name)
                return {"deleted": True}
    except VaultConflict as error:
        raise ProtocolError("write_conflict") from error
    except (OSError, UnicodeError, VaultError) as error:
        raise ProtocolError("write_failed") from error
    raise ProtocolError("unknown_operation")


def _path(request: dict, *, for_create: bool = False) -> Path:
    try:
        supplied = request.get("path")
        path = Path(supplied) if supplied is not None else default_vault_path()
        if not path.is_absolute():
            raise ProtocolError("invalid_request")
        return path.parent.resolve() / path.name if for_create else path.resolve()
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        raise ProtocolError("file_error") from error


def _regular_file(path: Path) -> None:
    if not stat.S_ISREG(path.stat().st_mode):
        raise OSError("expected a regular vault file")


def _response(session: _Session, line: bytes) -> dict:
    reply = {"version": VERSION, "id": None}
    try:
        if not line.endswith(b"\n"):
            raise ProtocolError("invalid_request")
        try:
            request = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)
        except (ValueError, RecursionError) as error:
            raise ProtocolError("invalid_request") from error
        if not isinstance(request, dict):
            raise ProtocolError("invalid_request")
        reply["id"] = _request_id(request.get("id"))
        operation = _validate(request)
        reply["result"] = session.execute(operation, request)
    except ProtocolError as error:
        reply["error"] = {"code": error.code, "message": str(error)}
    return reply


def _send(output: BinaryIO, reply: dict) -> None:
    output.write(json.dumps(reply, separators=(",", ":")).encode("ascii") + b"\n")
    output.flush()


def _read_requests(source: BinaryIO, requests: Queue, closed: Event) -> None:
    # Keep reading while an authenticator is waiting for touch or a Windows prompt.
    try:
        while line := source.readline(MAX_REQUEST_BYTES + 1):
            requests.put(line)
            if len(line) > MAX_REQUEST_BYTES:
                return
            del line
    finally:
        closed.set()
        requests.put(None)


def serve(source: BinaryIO, output: BinaryIO) -> int:
    """Serve one session until EOF or an oversized frame."""
    closed = Event()
    requests: Queue[bytes | None] = Queue(maxsize=1)
    Thread(target=_read_requests, args=(source, requests, closed), daemon=True).start()
    session = _Session(closed)
    while (line := requests.get()) is not None:
        if len(line) > MAX_REQUEST_BYTES:
            code = "request_too_large"
            _send(output, {"version": VERSION, "id": None,
                           "error": {"code": code, "message": ERROR_MESSAGES[code]}})
            return 1
        _send(output, _response(session, line))
        del line
    return 0


def main() -> int:
    """Run the protocol with stdout reserved for responses."""
    if sys.stdin.isatty() or sys.stdout.isatty() or len(sys.argv) != 1:
        print("The vault protocol requires redirected stdin and stdout and no arguments.",
              file=sys.stderr)
        return 2
    try:
        return serve(sys.stdin.buffer, sys.stdout.buffer)
    except (BrokenPipeError, KeyboardInterrupt):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
