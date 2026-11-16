"""Vault credentials and domain errors."""

from dataclasses import dataclass, field


class VaultError(Exception):
    """An error that can be shown to the user."""


class VaultConflict(VaultError):
    """The active snapshot has been superseded by another writer."""


class EntryEncodingError(VaultError):
    """A credential field contains invalid Unicode text."""


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

    def validate_text(self, previous: "Entry | None" = None) -> None:
        """Reject invalid UTF-8 in new values and preserve unchanged legacy fields."""
        for name, value in vars(self).items():
            if previous is None or value != getattr(previous, name):
                require_utf8(value)


def require_utf8(value: str) -> str:
    """Return text that can be encoded as UTF-8 without losing information."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise EntryEncodingError("This credential field contains invalid UTF-8 text.") from error
    return value
