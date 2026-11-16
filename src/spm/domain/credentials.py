"""Vault credentials and domain errors."""

from dataclasses import dataclass, field


class VaultError(Exception):
    """An error that can be shown to the user."""


class VaultConflict(VaultError):
    """The active snapshot has been superseded by another writer."""


@dataclass(frozen=True)
class Entry:
    """A saved credential and its metadata."""

    name: str
    password: str = field(repr=False)
    username: str = ""
    url: str = ""
    notes: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) for value in vars(self).values()):
            raise VaultError("Credential fields must be text.")
        if not self.name.strip():
            raise VaultError("Enter a name for the credential.")
        if not self.password:
            raise VaultError("Enter or generate a password.")
        object.__setattr__(self, "name", self.name.strip())
