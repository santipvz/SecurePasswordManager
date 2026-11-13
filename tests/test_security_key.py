"""Exercise both vault access methods and the WebAuthn verification boundary."""

import hashlib
import hmac
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from spm import security_key
from spm.vault import Entry, KeyEnrollment, Vault, VaultError, vault_has_security_key

MASTER = "Una frase maestra de prueba"
NEXT_MASTER = "Frase distinta para rotar la clave"
ENTRY = Entry("Correo", "credencial de ejemplo")


class VaultSecurityKeyTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "vault.spm"
        Vault.create(self.path, MASTER)
        self.vault = Vault(self.path, MASTER)
        self.vault.add([ENTRY])
        self.enrollment = KeyEnrollment(b"credential", b"s" * 32, b"k" * 32)
        self.device = Mock()
        self.device.derive.return_value = self.enrollment.secret

    def test_both_unlock_methods_can_use_the_same_vault_and_backup(self):
        self.assertFalse(vault_has_security_key(self.path))
        self.vault.add_security_key(MASTER, self.enrollment)
        self.assertTrue(vault_has_security_key(self.path))
        self.assertNotIn(self.enrollment.secret, self.path.read_bytes())
        with self.assertRaisesRegex(VaultError, "Remove the registered FIDO2 key"):
            self.vault.add_security_key(MASTER, self.enrollment)
        hardware_vault = Vault(self.path, security_key=self.device)
        self.device.derive.assert_called_once_with(self.enrollment.credential, self.enrollment.salt)
        self.assertEqual(hardware_vault.list(), [ENTRY])
        other = Entry("Trabajo", "otra credencial")
        hardware_vault.add([other])
        self.assertEqual(Vault(self.path, MASTER).list(), [ENTRY, other])
        backup = self.path.with_name("backup.spm")
        hardware_vault.backup(backup)
        self.assertEqual(Vault(backup, security_key=self.device).list(), [ENTRY, other])

    def test_wrong_device_and_tampered_hardware_header_are_rejected(self):
        self.vault.add_security_key(MASTER, self.enrollment)
        other_device = Mock()
        other_device.derive.return_value = b"w" * 32
        with self.assertRaisesRegex(VaultError, "could not unlock"):
            Vault(self.path, security_key=other_device)
        raw = bytearray(self.path.read_bytes())
        # The first PRF salt byte follows the magic, master salt, length, and credential.
        raw[22 + len(self.enrollment.credential)] ^= 1
        self.path.write_bytes(raw)
        with self.assertRaisesRegex(VaultError, "tampered with"):
            Vault(self.path, MASTER)
        with self.assertRaisesRegex(VaultError, "tampered with"):
            Vault(self.path, security_key=self.device)
        self.path.write_bytes(raw[:60])
        with self.assertRaisesRegex(VaultError, "vault format"):
            Vault(self.path, MASTER)

    def test_revocation_and_master_rotation_use_fresh_keys(self):
        self.vault.add_security_key(MASTER, self.enrollment)
        enrolled = self.path.read_bytes()
        with self.assertRaisesRegex(VaultError, "incorrect"):
            self.vault.remove_security_key(NEXT_MASTER)
        self.assertEqual(self.path.read_bytes(), enrolled)
        self.vault.remove_security_key(MASTER)
        self.assertNotEqual(self.path.read_bytes()[4:20], enrolled[4:20])
        self.assertFalse(vault_has_security_key(self.path))
        with self.assertRaisesRegex(VaultError, "no registered FIDO2 key"):
            Vault(self.path, security_key=self.device)
        self.device.derive.assert_not_called()
        self.assertEqual(Vault(self.path, MASTER).list(), [ENTRY])
        self.vault.add_security_key(MASTER, self.enrollment)
        self.vault.change_master(NEXT_MASTER)
        self.assertFalse(vault_has_security_key(self.path))
        self.assertEqual(Vault(self.path, NEXT_MASTER).list(), [ENTRY])


@unittest.skipUnless(security_key.FIDO2_AVAILABLE, "Requires the optional FIDO2 dependency")
class WebAuthnSecurityKeyTests(unittest.TestCase):
    def test_desktop_error_codes_cover_native_and_hid_failures(self):
        for cause, code in (
            (OSError("Disconnected"), "key_disconnected"),
            (security_key.CtapError(security_key.CtapError.ERR.PIN_INVALID), "pin_invalid"),
            (security_key.ClientError.ERR.DEVICE_INELIGIBLE(), "wrong_key"),
        ):
            with self.subTest(code=code):
                self.assertEqual(security_key._client_error(cause).code, code)
        for hresult, code in (
            (0x800704C7, "key_interrupted"),
            (0x80090011, "wrong_key"),
            (0x80090035, "key_disconnected"),
        ):
            with self.subTest(code=code):
                cause = OSError("Native WebAuthn error")
                cause.winerror = hresult - (1 << 32)
                error = security_key.ClientError.ERR.OTHER_ERROR(cause)
                self.assertEqual(security_key._client_error(error).code, code)

    def test_signed_assertion_requires_user_verification_and_prf_output(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from fido2.cose import ES256
        from fido2.webauthn import (
            AttestationObject, AttestedCredentialData, AuthenticationExtensionsClientOutputs,
            AuthenticationResponse, AuthenticatorAssertionResponse, AuthenticatorAttestationResponse,
            AuthenticatorData, CollectedClientData, RegistrationResponse,
        )

        private_key = ec.generate_private_key(ec.SECP256R1())
        credential = AttestedCredentialData.create(
            bytes(16), b"simulated credential", ES256.from_cryptography_key(private_key.public_key()),
        )
        rp_hash = hashlib.sha256(security_key.RP_ID.encode()).digest()
        flag = AuthenticatorData.FLAG
        flags = flag.UP | flag.UV
        verified = True
        include_prf = True

        def register(options, _cancel):
            self.assertEqual(options.authenticator_selection.user_verification, "required")
            self.assertEqual(options.authenticator_selection.authenticator_attachment, "cross-platform")
            self.assertEqual(options.authenticator_selection.resident_key, "discouraged")
            self.assertEqual(len(options.extensions["prf"]["eval"]["first"]), 32)
            self.assertTrue(options.extensions["enforceCredentialProtectionPolicy"])
            auth_data = AuthenticatorData.create(
                rp_hash, flags | flag.AT | flag.ED, 0, credential, extensions={"credProtect": 3},
            )
            client_data = CollectedClientData.create("webauthn.create", options.challenge, security_key.ORIGIN)
            return RegistrationResponse(
                raw_id=credential.credential_id,
                response=AuthenticatorAttestationResponse(
                    client_data=client_data, attestation_object=AttestationObject.create("none", auth_data, {}),
                ),
                client_extension_results=AuthenticationExtensionsClientOutputs({"prf": {"enabled": True}}),
            )

        def assert_credential(options, _cancel):
            self.assertEqual(options.user_verification, "required")
            self.assertEqual(options.allow_credentials[0].id, credential.credential_id)
            auth_data = AuthenticatorData.create(rp_hash, flags if verified else flag.UP, 1)
            client_data = CollectedClientData.create("webauthn.get", options.challenge, security_key.ORIGIN)
            signature = private_key.sign(auth_data + client_data.hash, ec.ECDSA(hashes.SHA256()))
            salt = options.extensions["prf"]["eval"]["first"]
            prf = {"prf": {"results": {"first": hmac.digest(b"mock secret", salt, "sha256")}}}
            response = AuthenticationResponse(
                raw_id=credential.credential_id,
                response=AuthenticatorAssertionResponse(
                    client_data=client_data, authenticator_data=auth_data, signature=signature,
                ),
                client_extension_results=AuthenticationExtensionsClientOutputs(prf if include_prf else {}),
            )
            return SimpleNamespace(get_response=lambda _index: response)

        client = SimpleNamespace(make_credential=register, get_assertion=assert_credential)
        device = security_key._FidoSecurityKey(client, None)
        enrollment = device.enroll()
        self.assertEqual(enrollment.credential, credential)
        self.assertEqual(device.derive(credential, enrollment.salt), enrollment.secret)
        include_prf = False
        with self.assertRaisesRegex(VaultError, "FIDO2 PRF secret"):
            device.derive(credential, enrollment.salt)
        include_prf = True
        verified = False
        with self.assertRaisesRegex(VaultError, "verify"):
            device.derive(credential, enrollment.salt)
