# Secure Password Manager

An offline password generator and encrypted vault for credentials, websites, and notes.

## Installation

Run these commands from the repository with Python 3.11 or later.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install .
cpass-desktop
```

In PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`. On Debian or Ubuntu, install `python3-tk` if your Python installation lacks Tkinter. The `cpass` and `python -m spm` commands work without Tkinter.

## Using the vault

1. Open `cpass-desktop` and create a vault with a long, unique master password. Use at least 15 characters.
2. Choose **New credential**. Paste an existing password or choose **Generate** and set its length and allowed symbols.
3. Search by name, username, or website. Select a credential to copy its password, reveal it for 15 seconds, edit it, or delete it.

The app attempts to clear the clipboard after 30 seconds if it still contains the copied password. **Lock** ends the session immediately. The vault also locks after five minutes of inactivity.

**Review vault** groups accounts that share a password and flags passwords shorter than 15 characters. The report runs locally, lists credential names, and provides a shortcut to the selected account. [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)

To generate a password without storing it, choose **Generator…** on the welcome screen or **File → Generate without saving…**. To create an encrypted backup, choose **File → Save encrypted backup…**. Use **Open file…** from the lock screen to open it.

## Unlocking with a YubiKey

Install the optional FIDO2 support with `python -m pip install ".[yubikey]"`.

1. Connect a USB security key that supports `hmac-secret` and `credProtect` and has a FIDO2 PIN or fingerprint verification set up. Linux requires permission to access the USB device. Windows requires WebAuthn support for PRF. [YubiKey compatibility](https://docs.yubico.com/hardware/yubikey/yk-tech-manual/yk5-apps-fido.html), [Linux device access](https://developers.yubico.com/python-fido2/#_installation)
2. Open the vault with the master password and choose **File → Register FIDO2 key…**. Follow the PIN or fingerprint prompt and touch the key when it blinks. Registration may require two touches.
3. Lock the vault and choose **Use FIDO2 key**. Keep the master password for recovery.

The vault supports one registered key. Removing it or changing the master password rotates the encryption key and removes the registration from the active vault. Existing backups retain their original unlock methods.

## Command line

```sh
cpass init
cpass generate --length 24
cpass add "Personal email" --username ana@example.org --generate
cpass list email
cpass audit
cpass show "Personal email"
cpass edit "Personal email" --generate --length 32 --no-symbols
cpass backup vault-backup.spm
cpass --vault vault-backup.spm list
cpass key-add
cpass --security-key list
cpass key-remove
cpass change-master
```

Omit `--generate` from `cpass add` to enter an account password without echo. Use `--prompt-password` to enter a replacement password with `cpass edit`. The `cpass show --password` command writes a password to standard output.

Import previous `.key` files with **File → Import .key files…** or `cpass import-key first.key second.key`. The import uses filenames as credential names. A duplicate or invalid file cancels the whole batch. The original files remain on disk in plaintext.

## Security and compatibility

- Passwords are generated with Python's `secrets` module. The default is 24 characters and the supported range is 12 to 256. [Python secrets documentation](https://docs.python.org/3/library/secrets.html)
- Argon2id derives a 256-bit key with a 16-byte random salt, 64 MiB of memory, three passes, and four lanes. AES-256-GCM authenticates and encrypts the vault, including credential names and notes. Each write uses a fresh nonce. [RFC 9106](https://www.rfc-editor.org/rfc/rfc9106.html), [AES-GCM documentation](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM)
- Both existing `.spm` versions remain supported. Version 1 uses the master password and version 2 adds a copy of the data key protected by FIDO2 PRF. A change to format or derivation parameters requires a new version and a compatibility test. [WebAuthn PRF](https://www.w3.org/TR/webauthn-3/#prf-extension)
- The application checks for concurrent changes before atomically replacing the vault file. Use a private directory on a local filesystem. The vault protects data at rest. A compromised computer or clipboard history can expose data while it is in use. The project has yet to undergo an independent security audit.

## Development

```sh
python -m pip install -e ".[yubikey]"
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
