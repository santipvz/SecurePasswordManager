"""Use cases for creating and working with an unlocked vault."""

from pathlib import Path
from typing import Iterable

from ..domain.credentials import Entry, VaultError
from .ports import KeyEnrollment, SecurityKey, UnlockState, VaultCodec, VaultStorage

MIN_MASTER_LENGTH = 15


def _validate_master(master: str) -> None:
    if len(master) < MIN_MASTER_LENGTH or not master.strip():
        raise VaultError(f"Use at least {MIN_MASTER_LENGTH} characters for the master password.")


def create_vault(storage: VaultStorage, codec: VaultCodec, master: str) -> None:
    """Create an empty encrypted vault."""
    _validate_master(master)
    storage.create(codec.seal({}, codec.new_state(master)))


class VaultSession:
    """Coordinate authenticated reads and conflict-checked writes."""

    def __init__(
        self, storage: VaultStorage, codec: VaultCodec,
        master: str | None, security_key: SecurityKey | None,
    ):
        if (master is None) == (security_key is None):
            raise TypeError("provide exactly one unlock method")
        self._storage = storage
        self._codec = codec
        self._snapshot = storage.read()
        self._state, self._entries = codec.open(self._snapshot, master, security_key)

    @property
    def has_security_key(self) -> bool:
        """Return whether a hardware credential is registered in this snapshot."""
        return self._state.hardware is not None

    def list(self, query: str = "") -> list[Entry]:
        """Search by name, username or URL."""
        query = query.casefold()
        matches = (
            entry for entry in self._entries.values()
            if any(query in value.casefold() for value in (entry.name, entry.username, entry.url))
        )
        return sorted(matches, key=lambda entry: entry.name.casefold())

    def get(self, name: str) -> Entry:
        """Look up a credential by name, ignoring case."""
        try:
            return self._entries[name.strip().casefold()]
        except KeyError as error:
            raise VaultError("Credential not found.") from error

    def add(self, entries: Iterable[Entry]) -> None:
        """Add a batch of credentials as a single update."""
        updated = self._entries.copy()
        for entry in entries:
            index = entry.name.casefold()
            if index in updated:
                raise VaultError(f"A credential named {entry.name!r} already exists.")
            updated[index] = entry
        self._commit(updated, self._state)

    def edit(self, name: str, entry: Entry) -> None:
        """Replace a credential, optionally changing its name."""
        index = self.get(name).name.casefold()
        updated = self._entries.copy()
        del updated[index]
        new_index = entry.name.casefold()
        if new_index in updated:
            raise VaultError(f"A credential named {entry.name!r} already exists.")
        updated[new_index] = entry
        self._commit(updated, self._state)

    def delete(self, name: str) -> None:
        """Remove a credential from the active vault."""
        updated = self._entries.copy()
        del updated[self.get(name).name.casefold()]
        self._commit(updated, self._state)

    def change_master(self, master: str) -> None:
        """Rotate the data key and discard any wrap for the previous key."""
        _validate_master(master)
        self._commit(self._entries, self._codec.new_state(master))

    def add_security_key(self, master: str, enrollment: KeyEnrollment) -> None:
        """Register a verified authenticator and rotate to a fresh data key."""
        if self.has_security_key:
            raise VaultError("Remove the registered FIDO2 key before adding another.")
        self.verify_master(master)
        _validate_master(master)
        self._commit(self._entries, self._codec.new_state(master, enrollment))

    def remove_security_key(self, master: str) -> None:
        """Remove the hardware unlock method and rotate to a fresh data key."""
        if not self.has_security_key:
            raise VaultError("This vault has no registered FIDO2 key.")
        self.verify_master(master)
        self.change_master(master)

    def verify_master(self, master: str) -> None:
        """Require the master password for this unlocked snapshot again."""
        if not self._codec.master_matches(master, self._state):
            raise VaultError("The current master password is incorrect.")

    def backup(self, destination: Path) -> None:
        """Save the authenticated, encrypted snapshot to a new file."""
        self._storage.backup(self._snapshot, destination)

    def _commit(self, entries: dict[str, Entry], state: UnlockState) -> None:
        data = self._codec.seal(entries, state)
        self._storage.replace(self._snapshot, data)
        self._snapshot, self._entries, self._state = data, entries, state
