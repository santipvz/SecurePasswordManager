"""The authenticated SPM v1 and v2 file formats."""

import json
from dataclasses import asdict, dataclass
from secrets import compare_digest, token_bytes

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..application.ports import KEY_SIZE, PRF_SALT_SIZE, KeyEnrollment, SecurityKey, UnlockState
from ..domain.credentials import Entry, VaultError

MAX_VAULT_SIZE = 16 * 1024 * 1024
MAGIC = b"SPM\x01"
HARDWARE_MAGIC = b"SPM\x02"
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
HEADER_SIZE = len(MAGIC) + SALT_SIZE + NONCE_SIZE
MAX_CREDENTIAL_SIZE = 4096


@dataclass(frozen=True)
class _HardwareSlot:
    credential: bytes
    salt: bytes
    nonce: bytes
    wrapped_key: bytes

    def encode(self) -> bytes:
        """Encode the version 2 hardware header."""
        return (
            len(self.credential).to_bytes(2, "big") + self.credential
            + self.salt + self.nonce + self.wrapped_key
        )

    @staticmethod
    def _aad(master_salt: bytes, prf_salt: bytes, credential: bytes) -> bytes:
        return b"SPM\x02 FIDO2 wrap\x00" + master_salt + prf_salt + credential

    @classmethod
    def wrap(cls, enrollment: KeyEnrollment, master_salt: bytes, key: bytes):
        """Encrypt a data key with the authenticator's PRF output."""
        if (not 0 < len(enrollment.credential) <= MAX_CREDENTIAL_SIZE
                or len(enrollment.salt) != PRF_SALT_SIZE or len(enrollment.secret) != KEY_SIZE):
            raise VaultError("The FIDO2 key returned an incompatible credential.")
        nonce = token_bytes(NONCE_SIZE)
        aad = cls._aad(master_salt, enrollment.salt, enrollment.credential)
        wrapped = AESGCM(enrollment.secret).encrypt(nonce, key, aad)
        return cls(enrollment.credential, enrollment.salt, nonce, wrapped)

    def unlock(self, master_salt: bytes, security_key: SecurityKey) -> bytes:
        """Obtain a verified PRF output and decrypt the wrapped key."""
        secret = security_key.derive(self.credential, self.salt)
        if len(secret) != KEY_SIZE:
            raise VaultError("The FIDO2 key returned an incompatible key.")
        try:
            aad = self._aad(master_salt, self.salt, self.credential)
            return AESGCM(secret).decrypt(self.nonce, self.wrapped_key, aad)
        except InvalidTag as error:
            raise VaultError(
                "The FIDO2 key could not unlock this vault or the file was tampered with."
            ) from error


@dataclass(frozen=True)
class _EncryptedVault:
    salt: bytes
    hardware: _HardwareSlot | None
    header: bytes
    payload: bytes


def _derive_key(master: str, salt: bytes) -> bytes:
    # The parameters are part of both file versions. Changes require a new version.
    return hash_secret_raw(
        master.encode("utf-8"), salt, time_cost=3, memory_cost=64 * 1024,
        parallelism=4, hash_len=32, type=Type.ID, version=19,
    )


def _encrypt(
    entries: dict[str, Entry], salt: bytes, key: bytes, hardware: bytes | None = None,
) -> bytes:
    nonce = token_bytes(NONCE_SIZE)
    prefix = MAGIC + salt if hardware is None else HARDWARE_MAGIC + salt + hardware
    header = prefix + nonce
    payload = json.dumps([asdict(entry) for entry in entries.values()]).encode("utf-8")
    if len(payload) + len(header) + TAG_SIZE > MAX_VAULT_SIZE:
        raise VaultError("The vault exceeds the 16 MiB size limit.")
    return header + AESGCM(key).encrypt(nonce, payload, header)


def _split_vault(data: bytes) -> _EncryptedVault:
    format_error = "Damaged or unsupported vault format."
    if len(data) < HEADER_SIZE + TAG_SIZE:
        raise VaultError(format_error)
    salt = data[len(MAGIC):len(MAGIC) + SALT_SIZE]
    if data.startswith(MAGIC):
        return _EncryptedVault(salt, None, data[:HEADER_SIZE], data[HEADER_SIZE:])
    if not data.startswith(HARDWARE_MAGIC):
        raise VaultError(format_error)
    start = len(HARDWARE_MAGIC) + SALT_SIZE
    credential_size = int.from_bytes(data[start:start + 2], "big")
    salt_start = start + 2 + credential_size
    nonce_start = salt_start + PRF_SALT_SIZE
    wrapped_start = nonce_start + NONCE_SIZE
    wrapped_end = wrapped_start + KEY_SIZE + TAG_SIZE
    header_end = wrapped_end + NONCE_SIZE
    if not 0 < credential_size <= MAX_CREDENTIAL_SIZE or len(data) < header_end + TAG_SIZE:
        raise VaultError(format_error)
    slot = _HardwareSlot(
        data[start + 2:salt_start], data[salt_start:nonce_start],
        data[nonce_start:wrapped_start], data[wrapped_start:wrapped_end],
    )
    return _EncryptedVault(salt, slot, data[:header_end], data[header_end:])


def _decrypt(encrypted: _EncryptedVault, key: bytes, error_message: str) -> dict[str, Entry]:
    try:
        header = encrypted.header
        payload = AESGCM(key).decrypt(header[-NONCE_SIZE:], encrypted.payload, header)
    except InvalidTag as error:
        raise VaultError(error_message) from error
    try:
        records = json.loads(payload)
        if not isinstance(records, list):
            raise ValueError("expected a list")
        entries = {}
        for record in records:
            entry = Entry(**record)
            index = entry.name.casefold()
            if index in entries:
                raise ValueError("duplicate entry name")
            entries[index] = entry
    except (TypeError, ValueError, RecursionError, VaultError) as error:
        raise VaultError("Damaged or unsupported vault contents.") from error
    return entries



class SpmCodec:
    """Encrypt and decrypt both supported versions of the vault format."""

    @staticmethod
    def new_state(master: str, enrollment: KeyEnrollment | None = None) -> UnlockState:
        """Derive a new data key and optionally wrap it using the authenticator's PRF."""
        salt = token_bytes(SALT_SIZE)
        key = _derive_key(master, salt)
        hardware = None
        if enrollment is not None:
            hardware = _HardwareSlot.wrap(enrollment, salt, key).encode()
        return UnlockState(salt, key, hardware)

    @staticmethod
    def master_matches(master: str, state: UnlockState) -> bool:
        """Derive and compare the supplied master password in constant time."""
        return compare_digest(state.key, _derive_key(master, state.salt))

    @staticmethod
    def seal(entries: dict[str, Entry], state: UnlockState) -> bytes:
        """Encrypt and authenticate a snapshot with a fresh nonce."""
        return _encrypt(entries, state.salt, state.key, state.hardware)

    @staticmethod
    def open(
        data: bytes, master: str | None, security_key: SecurityKey | None,
    ) -> tuple[UnlockState, dict[str, Entry]]:
        """Authenticate and decode a snapshot using the selected unlock method."""
        encrypted = _split_vault(data)
        if security_key is not None:
            if encrypted.hardware is None:
                raise VaultError("This vault has no registered FIDO2 key.")
            key = encrypted.hardware.unlock(encrypted.salt, security_key)
            error_message = "The vault was tampered with or does not match this FIDO2 key."
        else:
            assert master is not None
            key = _derive_key(master, encrypted.salt)
            error_message = "Incorrect master password or the vault was tampered with."
        hardware = encrypted.hardware.encode() if encrypted.hardware is not None else None
        return UnlockState(encrypted.salt, key, hardware), _decrypt(encrypted, key, error_message)
