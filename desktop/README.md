# Desktop app

The native app checks the default vault and can open another `.spm` file or create a new one through the system file dialog. Creating a vault requires a master password of at least 15 characters. An existing file is preserved if you select its name while creating a vault.

If the selected vault has a registered YubiKey, choose **Unlock with YubiKey**. On Windows, follow the system security prompt. On Linux and macOS, enter the FIDO2 PIN if your key requires one and touch the key when it blinks. You can cancel the attempt or switch back to the master password. To register a new key in this version, use the Python app.

Search an unlocked vault by name, username, or website. Select an entry to view its details, edit it, or delete it after confirmation. Leave the password field blank when editing to keep the saved password.

Passwords stay hidden until you reveal them. A reveal lasts 10 seconds and ends when you leave the details view or the window loses focus. Copying sends the password directly to the system clipboard through Rust. The app attempts to clear its copy after 30 seconds or when the vault locks, provided the clipboard still contains the copied value.

Choose **Lock vault** to end the session immediately. The app also locks after five minutes without keyboard or pointer input.

Install Python 3.11 or later, Node.js 22.12 or later in the 22 series, a stable Rust toolchain, and the native packages listed in the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/). Activate a Python virtual environment and run these commands from the repository root:

```sh
python -m pip install ".[yubikey]" pyinstaller==6.22.3
python desktop/scripts/bundle_vault.py
cd desktop
npm ci
npm run tauri dev
```

On Debian with system Python 3.11, install `libpython3.11` for PyInstaller. Reinstall the Python package and rebuild the vault process after changing the Python core.

From this directory, run `npm run dev` and open `http://127.0.0.1:1420` to review the browser demo with fictional credentials. `npm run check` checks Svelte and TypeScript, and `npm run build` bundles the local frontend assets. Run `cargo test --locked --features custom-protocol --manifest-path src-tauri/Cargo.toml` after building both the vault process and frontend to test the bridge.
