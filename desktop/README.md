# Desktop app

The native app checks the default vault and can open another `.spm` file or create a new one through the system file dialog. Creating a vault requires a master password of at least 15 characters. An existing file is preserved if you select its name while creating a vault.

If the selected vault has a registered YubiKey, choose **Unlock with YubiKey**. On Windows, follow the system security prompt. On Linux and macOS, enter the FIDO2 PIN if your key requires one and touch the key when it blinks. You can cancel the attempt or switch back to the master password.

Search an unlocked vault by name, username, or website. Select an entry to view its details, edit it, or delete it after confirmation. Leave the password field blank when editing to keep the saved password.

Passwords stay hidden until you reveal them. A reveal lasts 10 seconds and ends when you leave the details view or the window loses focus. Copying sends the password directly to the system clipboard through Rust. The app attempts to clear its copy after 30 seconds or when the vault locks, provided the clipboard still contains the copied value.

Open **Password generator** on the lock screen to generate a password without opening a vault. In the credential editor, choose **Open password generator** and **Use password** to fill the password field. The generator supports 12 to 256 characters and optional symbols.

Choose **Review passwords** to check the unlocked vault for short and exactly reused passwords. Select a result to open the corresponding credential. The review runs locally and leaves the vault file unchanged.

Open **Vault settings** to save an encrypted backup or open an existing backup as a separate vault. A backup keeps the unlock methods from the moment it was saved. You can also import up to 64 legacy `.key` files at a time. The import saves the whole batch together and leaves the original plaintext files on disk.

Use **Vault settings** to register or remove a YubiKey with the current master password. Changing the master password rotates the active vault key and removes the active YubiKey registration. You can then register a key again. Keep the previous unlock method if you need to open an older backup.

Choose **Lock vault** to end the session immediately. The app also locks after five minutes without keyboard or pointer input.

Install Python 3.11 or later, Node.js 22.12 or later in the 22 series, a stable Rust toolchain, and the native packages listed in the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/). Install the version of uv used by CI and run these commands from the repository root.

```sh
uv sync --locked --no-install-project --extra yubikey --group build --group desktop-build
uv sync --locked --no-build-isolation-package sec-pass-manager --extra yubikey --group build --group desktop-build
uv run --no-sync python desktop/scripts/bundle_vault.py
cd desktop
npm ci
npm run tauri dev
```

On Debian with system Python 3.11, install `libpython3.11` for PyInstaller. Rebuild the vault process after changing the Python core. See [CI checks](../CI.md) for the current uv version and performance commands.

From this directory, run `npm run dev` and open `http://127.0.0.1:1420` to review the browser demo with fictional credentials. `npm run check` checks Svelte and TypeScript, and `npm run build` bundles the local frontend assets. Run `cargo test --locked --features custom-protocol --manifest-path src-tauri/Cargo.toml` after building both the vault process and frontend to test the bridge.
