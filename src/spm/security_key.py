"""Local WebAuthn registration and PRF evaluation with an external authenticator."""

import sys
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from secrets import token_bytes
from threading import Event

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


def _client_error(error) -> str:
    if isinstance(error, PinRequiredError):
        return "Enter the FIDO2 key PIN."
    cause = error.cause if isinstance(error, ClientError) else error
    if isinstance(cause, CtapError):
        pin_required = "Set up a FIDO2 PIN on the key."
        messages = {
            CtapError.ERR.PIN_INVALID: "The FIDO2 PIN is incorrect.",
            CtapError.ERR.PIN_AUTH_BLOCKED: "The PIN is temporarily blocked. Reconnect the key.",
            CtapError.ERR.PIN_BLOCKED: "The PIN is blocked. Use the master password to unlock.",
            CtapError.ERR.PIN_NOT_SET: pin_required,
            CtapError.ERR.PUAT_REQUIRED: pin_required,
        }
        if cause.code in messages:
            return messages[cause.code]
    if isinstance(error, ClientError):
        match error.code:
            case ClientError.ERR.DEVICE_INELIGIBLE:
                return "The connected key has no credential for this vault."
            case ClientError.ERR.TIMEOUT:
                return "The FIDO2 operation timed out or was cancelled."
            case ClientError.ERR.CONFIGURATION_UNSUPPORTED:
                return "The key requires a PIN or does not support FIDO2 PRF."
    return "The FIDO2 operation failed. Check the connection and PIN."


@contextmanager
def _fido_operation():
    try:
        yield
    except (ClientError, CtapError) as error:
        raise VaultError(_client_error(error)) from error
    except OSError as error:
        raise VaultError(
            "The system could not complete the FIDO2 operation. Check the connection."
        ) from error
    except (ValueError, TypeError, IndexError) as error:
        raise VaultError("Could not verify the FIDO2 key response.") from error


class _FidoSecurityKey:
    def __init__(self, client, cancel):
        self._client = client
        self._cancel = cancel
        self._server = Fido2Server(
            PublicKeyCredentialRpEntity(id=RP_ID, name="Secure Password Manager"),
            verify_origin=lambda origin: origin == ORIGIN,
        )
        self._server.timeout = TIMEOUT_MS

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
            response = self._client.make_credential(options.public_key, self._cancel)
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
            response = self._client.get_assertion(request, self._cancel).get_response(0)
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
        # Windows owns the native dialog and its Cancel button.
        yield _FidoSecurityKey(WindowsClient(collector, handle=window), None)
        return

    with ExitStack() as stack:
        devices = []
        with _fido_operation():
            for device in CtapHidDevice.list_devices():
                stack.callback(device.close)
                devices.append(device)
            if not devices:
                raise VaultError(
                    "Connect a FIDO2 key over USB and check device permissions."
                )
            if len(devices) != 1:
                raise VaultError("Connect only the FIDO2 key you want to use.")
            client = Fido2Client(
                devices[0], collector, _Interaction(read_pin, notify),
                extensions=[HmacSecretExtension(), CredProtectExtension()],
            )
            if "hmac-secret" not in client.info.extensions:
                raise VaultError("The connected key does not support FIDO2 hmac-secret.")
            if client.info.options.get("clientPin") is False and not client.info.options.get("uv"):
                raise VaultError(
                    "Set up the key's FIDO2 PIN before using it with the vault."
                )
        yield _FidoSecurityKey(client, cancel)
