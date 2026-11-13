"""Composition of the local vault and compatibility exports for existing callers."""

from pathlib import Path

from .adapters.spm_codec import HARDWARE_MAGIC, MAGIC, SpmCodec
from .adapters.vault_files import VaultFile, default_vault_path, read_legacy, vault_has_security_key
from .application.ports import KeyEnrollment, SecurityKey
from .application.vault_session import MIN_MASTER_LENGTH, VaultSession, create_vault
from .domain.credentials import Entry, VaultConflict, VaultError

__all__ = [
    "Entry", "HARDWARE_MAGIC", "KeyEnrollment", "MAGIC", "MIN_MASTER_LENGTH", "Vault",
    "VaultConflict", "VaultError", "default_vault_path", "read_legacy", "vault_has_security_key",
]


class Vault(VaultSession):
    """Open the local encrypted vault using the standard adapters."""

    def __init__(
        self, path: Path, master: str | None = None, *, security_key: SecurityKey | None = None,
    ):
        self.path = path.expanduser().resolve()
        super().__init__(VaultFile(self.path), SpmCodec(), master, security_key)

    @staticmethod
    def create(path: Path, master: str) -> None:
        """Create an empty vault without overwriting an existing file."""
        create_vault(VaultFile(path), SpmCodec(), master)
