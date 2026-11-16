"""Interfaces used by the vault use cases."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..domain.credentials import Entry

KEY_SIZE = 32
PRF_SALT_SIZE = 32


class SecurityKey(Protocol):
    """A registered authenticator capable of evaluating its credential's PRF."""

    def derive(self, credential: bytes, salt: bytes) -> bytes:
        """Return a verified 32-byte PRF output for this credential."""


@dataclass(frozen=True)
class KeyEnrollment:
    """Credential and PRF output obtained before updating the vault."""

    credential: bytes
    salt: bytes
    secret: bytes = field(repr=False)



@dataclass(frozen=True)
class UnlockState:
    """Key material and the optional opaque hardware slot of an unlocked vault."""

    salt: bytes
    key: bytes = field(repr=False)
    hardware: bytes | None = None


class VaultCodec(Protocol):
    """Seal vault data and recover it using either unlock method."""

    def new_state(self, master: str, enrollment: KeyEnrollment | None = None) -> UnlockState:
        """Derive fresh key material, optionally wrapping it for a hardware credential."""

    def master_matches(self, master: str, state: UnlockState) -> bool:
        """Check the master password against the active key."""

    def seal(self, entries: dict[str, Entry], state: UnlockState) -> bytes:
        """Return an authenticated, encrypted snapshot."""

    def open(
        self, data: bytes, master: str | None, security_key: SecurityKey | None,
    ) -> tuple[UnlockState, dict[str, Entry]]:
        """Authenticate and decode an encrypted snapshot."""


class VaultStorage(Protocol):
    """Read and persist encrypted snapshots without overwriting concurrent changes."""

    def read(self) -> bytes:
        """Read the current snapshot."""

    def create(self, data: bytes) -> None:
        """Create the vault without replacing existing data."""

    def replace(self, expected: bytes, data: bytes) -> None:
        """Replace the current snapshot only if it still matches the expected bytes."""

    def backup(self, expected: bytes, destination: Path) -> None:
        """Copy the current snapshot to a new destination if it still matches."""
