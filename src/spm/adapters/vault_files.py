"""Filesystem operations for encrypted vaults and legacy credentials."""

import errno
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from filelock import FileLock, Timeout

from ..domain.credentials import Entry, VaultConflict, VaultError
from ..paths import user_data_directory
from .spm_codec import HARDWARE_MAGIC, MAX_VAULT_SIZE

MAX_LEGACY_SIZE = 1024 * 1024


def default_vault_path() -> Path:
    """Return the vault path in the current user's application data directory."""
    return user_data_directory() / "SecurePasswordManager" / "vault.spm"


def vault_has_security_key(path: Path) -> bool:
    """Check whether the file advertises FIDO2 unlocking without opening a session."""
    try:
        with path.expanduser().open("rb") as stream:
            return stream.read(len(HARDWARE_MAGIC)) == HARDWARE_MAGIC
    except OSError:
        return False


def _read_vault(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_VAULT_SIZE + 1)
    except FileNotFoundError as error:
        raise VaultError("Vault not found. Create one or open an existing backup.") from error
    if len(data) > MAX_VAULT_SIZE:
        raise VaultError("The vault exceeds the 16 MiB size limit.")
    return data


def _sync_directory(path: Path) -> None:
    if os.name == "posix":
        directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        except OSError as error:
            if error.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
        finally:
            os.close(directory)


def _write_and_sync(stream: BinaryIO, data: bytes) -> None:
    stream.write(data)
    stream.flush()
    os.fsync(stream.fileno())


def _publish_new(temporary: Path, path: Path, data: bytes) -> None:
    if os.name == "nt":
        temporary.rename(path)  # Windows rename fails if the destination already exists.
        return
    try:
        os.link(temporary, path)
    except OSError as error:
        if error.errno not in (errno.EPERM, errno.ENOTSUP):
            raise
        # Filesystems such as exFAT lack hard links. Reserve a new name without overwriting.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                _write_and_sync(stream, data)
        except BaseException:
            path.unlink()
            raise


def _write_vault(path: Path, data: bytes, *, create: bool = False) -> None:
    # The temporary file contains ciphertext and has owner-only permissions on POSIX.
    stream = NamedTemporaryFile(dir=path.parent, prefix=".spm-", delete=False)
    temporary = Path(stream.name)
    try:
        with stream:
            _write_and_sync(stream, data)
        if create:
            _publish_new(temporary, path, data)
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    _sync_directory(path.parent)


def read_legacy(path: Path) -> Entry:
    """Read an original .key file without modifying it."""
    with path.expanduser().open("rb") as stream:
        raw = stream.read(MAX_LEGACY_SIZE + 1)
    try:
        if len(raw) > MAX_LEGACY_SIZE:
            raise ValueError("legacy file too large")
        content = raw.decode("utf-8").replace("\r\n", "\n")
        user, separator, password = content.rpartition("\nPassword: ")
        if not user.startswith("User: ") or not separator or "\n" in password.rstrip("\n"):
            raise ValueError("invalid legacy format")
        return Entry(name=path.stem, username=user[6:], password=password.rstrip("\n"))
    except (ValueError, VaultError) as error:
        raise VaultError(
            f"{path.name!r} does not contain a valid .key credential."
        ) from error



class VaultFile:
    """Store encrypted snapshots using atomic replacement and an interprocess lock."""

    def __init__(self, path: Path):
        self.path = path.expanduser().absolute()

    def read(self) -> bytes:
        """Read the current vault file."""
        return _read_vault(self.path)

    def create(self, data: bytes) -> None:
        """Publish a new vault while preserving any existing file."""
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            _write_vault(self.path, data, create=True)
        except FileExistsError as error:
            raise VaultError("A file already exists at the vault path.") from error

    def replace(self, expected: bytes, data: bytes) -> None:
        """Replace a snapshot only if no other writer has changed it."""
        lock = FileLock(str(self.path) + ".lock", timeout=2, mode=0o600)
        try:
            with lock:
                self._check_snapshot(expected)
                _write_vault(self.path, data)
        except Timeout as error:
            raise VaultError("The vault is busy. Try again.") from error

    def backup(self, expected: bytes, destination: Path) -> None:
        """Publish an encrypted copy of the current snapshot at a new path."""
        self._check_snapshot(expected)
        try:
            _write_vault(destination.expanduser().absolute(), expected, create=True)
        except FileExistsError as error:
            raise VaultError("A file already exists at the backup destination.") from error

    def _check_snapshot(self, expected: bytes) -> None:
        if self.read() != expected:
            raise VaultConflict("The vault changed. Reopen it before saving.")
