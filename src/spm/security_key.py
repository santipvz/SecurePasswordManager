"""Local WebAuthn registration and PRF evaluation with an external authenticator."""

import sys
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from secrets import token_bytes
from threading import Event, Thread

from .application.ports import KEY_SIZE, PRF_SALT_SIZE, KeyEnrollment
from .domain.credentials import VaultError

try:
    from fido2.client import ClientError, DefaultClientDataCollector, Fido2Client, PinRequiredError
    from fido2.ctap import CtapError
    from fido2.ctap2.extensions import (
        AuthenticatorExtensionsPRFOutputs, CredProtectExtension, HmacSecretExtension,
    )
    from fido2.hid import CtapHidDevice
    from fido2.server import Fido2Server
    from fido2.webauthn import (
        AttestedCredentialData, AuthenticatorAttachment, PublicKeyCredentialHint,
        PublicKeyCredentialRpEntity, PublicKeyCredentialUserEntity, ResidentKeyRequirement,
        UserVerificationRequirement,
    )
except ImportError:
    FIDO2_AVAILABLE = False
else:
    FIDO2_AVAILABLE = True

RP_ID = "secure-password-manager.invalid"
ORIGIN = f"https://{RP_ID}"
TIMEOUT_MS = 45_000
CRED_PROTECT_REQUIRED = 3


class SecurityKeyError(VaultError):
    """A hardware error with a stable code for desktop callers."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _Interaction:
    def __init__(self, read_pin, notify):
        self._read_pin = read_pin
        self._notify = notify

    def prompt_up(self):
        """Notify the user when the key requests a touch."""
        self._notify("Touch the FIDO2 key when it blinks.")

    def request_pin(self, _permissions, _rp_id):
        """Provide a PIN for this request, if supplied."""
        return self._read_pin() or None

    def request_uv(self, _permissions, _rp_id):
        """Allow verification on the device, such as a fingerprint."""
        return True


def _client_error(error) -> SecurityKeyError:
    if isinstance(error, PinRequiredError):
        return SecurityKeyError("pin_required", "Enter the FIDO2 key PIN.")
    cause = error.cause if isinstance(error, ClientError) else error
    if isinstance(cause, CtapError):
        pin_required = ("key_setup_required", "Set up a FIDO2 PIN on the key.")
        messages = {
            CtapError.ERR.PIN_INVALID: ("pin_invalid", "The FIDO2 PIN is incorrect."),
            CtapError.ERR.PIN_AUTH_BLOCKED: (
                "pin_blocked", "The PIN is temporarily blocked. Reconnect the key.",
            ),
            CtapError.ERR.PIN_BLOCKED: (
                "pin_blocked", "The PIN is blocked. Use the master password to unlock.",
            ),
            CtapError.ERR.PIN_NOT_SET: pin_required,
            CtapError.ERR.PUAT_REQUIRED: pin_required,
        }
        if cause.code in messages:
            return SecurityKeyError(*messages[cause.code])
    if isinstance(cause, OSError):
        return _connection_error(cause)
    if isinstance(error, ClientError):
        messages = {
            ClientError.ERR.DEVICE_INELIGIBLE: (
                "wrong_key", "The connected key has no credential for this vault.",
            ),
            ClientError.ERR.TIMEOUT: (
                "key_interrupted", "The FIDO2 operation timed out or was cancelled.",
            ),
            ClientError.ERR.CONFIGURATION_UNSUPPORTED: (
                "key_unsupported", "The key requires a PIN or does not support FIDO2 PRF.",
            ),
        }
        if error.code in messages:
            return SecurityKeyError(*messages[error.code])
    return SecurityKeyError(
        "key_failed", "The FIDO2 operation failed. Check the connection and PIN.",
    )


def _connection_error(error: OSError) -> SecurityKeyError:
    # Windows WebAuthn reports these HRESULT values through ctypes.
    match (getattr(error, "winerror", None) or 0) & 0xffffffff:
        case 0x800704C7 | 0x80090036 | 0x800705B4:
            return SecurityKeyError("key_interrupted", "The security key request ended.")
        case 0x80090011:
            return SecurityKeyError("wrong_key", "Use the security key registered for this vault.")
        case _:
            return SecurityKeyError("key_disconnected", "Check the security key connection.")


@contextmanager
def _fido_operation():
    try:
        yield
    except (ClientError, CtapError) as error:
        raise _client_error(error) from error
    except OSError as error:
        raise _client_error(error) from error
    except (ValueError, TypeError, IndexError) as error:
        raise SecurityKeyError("key_failed", "Could not verify the FIDO2 key response.") from error


class _FidoSecurityKey:
    def __init__(self, client, cancel, *, native_prompt=False):
        self._client = client
        self._cancel = cancel
        self._native_prompt = native_prompt
        self._server = Fido2Server(
            PublicKeyCredentialRpEntity(id=RP_ID, name="Secure Password Manager"),
            verify_origin=lambda origin: origin == ORIGIN,
        )
        self._server.timeout = TIMEOUT_MS

    @contextmanager
    def _ceremony(self):
        if not self._native_prompt or self._cancel is None:
            yield self._cancel
            return

        # WindowsClient sets its event on success. Bridge cancellation to a
        # fresh event for each WebAuthn call without changing the caller's event.
        if self._cancel.is_set():
            raise SecurityKeyError("key_interrupted", "The security key request ended.")
        native_cancel = Event()

        def relay_cancellation():
            while not native_cancel.is_set():
                if self._cancel.wait(0.025):
                    native_cancel.set()

        relay = Thread(target=relay_cancellation, daemon=True)
        relay.start()
        try:
            yield native_cancel
        finally:
            native_cancel.set()
            relay.join()

    def enroll(self) -> KeyEnrollment:
        """Register a non-discoverable credential and prove it can produce a PRF secret."""
        salt = token_bytes(PRF_SALT_SIZE)
        with _fido_operation():
            options, state = self._server.register_begin(
                PublicKeyCredentialUserEntity(id=token_bytes(32), name="Local vault"),
                resident_key_requirement=ResidentKeyRequirement.DISCOURAGED,
                user_verification=UserVerificationRequirement.REQUIRED,
                authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
                extensions={
                    "prf": {"eval": {"first": salt}},
                    "credentialProtectionPolicy": "userVerificationRequired",
                    "enforceCredentialProtectionPolicy": True,
                },
            )
            with self._ceremony() as cancel:
                response = self._client.make_credential(options.public_key, cancel)
            auth_data = self._server.register_complete(state, response)
            prf = AuthenticatorExtensionsPRFOutputs.from_dict(response.client_extension_results.prf)
            if prf is None or not prf.enabled or auth_data.credential_data is None:
                raise VaultError("The key or system does not support FIDO2 PRF.")
            if (auth_data.extensions or {}).get("credProtect") != CRED_PROTECT_REQUIRED:
                raise VaultError("The key did not confirm required PIN or fingerprint protection.")
            credential = bytes(auth_data.credential_data)
        return KeyEnrollment(credential, salt, self.derive(credential, salt))

    def derive(self, credential: bytes, salt: bytes) -> bytes:
        """Authenticate this exact credential with user verification before using its PRF."""
        with _fido_operation():
            stored = AttestedCredentialData(credential)
            options, state = self._server.authenticate_begin(
                [stored], user_verification=UserVerificationRequirement.REQUIRED,
                extensions={"prf": {"eval": {"first": salt}}},
            )
            request = replace(options.public_key, hints=[PublicKeyCredentialHint.SECURITY_KEY])
            with self._ceremony() as cancel:
                response = self._client.get_assertion(request, cancel).get_response(0)
            self._server.authenticate_complete(state, [stored], response)
            prf = AuthenticatorExtensionsPRFOutputs.from_dict(response.client_extension_results.prf)
            if prf is None or prf.results is None or len(prf.results.first) != KEY_SIZE:
                raise VaultError("The key or system did not return a FIDO2 PRF secret.")
            return prf.results.first


@contextmanager
def open_security_key(
    read_pin: Callable[[], str | None], notify: Callable[[str], None],
    *, cancel: Event | None = None, window: int | None = None,
):
    """Use the Windows security prompt or a single CTAP HID device."""
    if not FIDO2_AVAILABLE:
        raise VaultError("Install YubiKey support with python -m pip install '.[yubikey]'.")
    collector = DefaultClientDataCollector(
        ORIGIN, verify=lambda rp_id, origin: rp_id == RP_ID and origin == ORIGIN,
    )
    if sys.platform == "win32":
        try:
            from fido2.client.windows import WindowsClient  # pylint: disable=import-outside-toplevel
        except (ImportError, OSError) as error:
            raise VaultError("Windows could not access the key through WebAuthn.") from error
        if not WindowsClient.is_available():
            raise VaultError("This version of Windows does not provide access to FIDO2 keys.")
        yield _FidoSecurityKey(WindowsClient(collector, handle=window), cancel, native_prompt=True)
        return

    with ExitStack() as stack:
        devices = []
        with _fido_operation():
            for device in CtapHidDevice.list_devices():
                stack.callback(device.close)
                devices.append(device)
            if not devices:
                raise SecurityKeyError(
                    "key_disconnected", "Connect a FIDO2 key and check device permissions.",
                )
            if len(devices) != 1:
                raise SecurityKeyError(
                    "multiple_keys", "Connect only the FIDO2 key you want to use.",
                )
            client = Fido2Client(
                devices[0], collector, _Interaction(read_pin, notify),
                extensions=[HmacSecretExtension(), CredProtectExtension()],
            )
            if "hmac-secret" not in client.info.extensions:
                raise SecurityKeyError(
                    "key_unsupported", "The connected key does not support FIDO2 hmac-secret.",
                )
            if client.info.options.get("clientPin") is False and not client.info.options.get("uv"):
                raise SecurityKeyError(
                    "key_setup_required", "Set up the key's FIDO2 PIN before using it.",
                )
        yield _FidoSecurityKey(client, cancel)
