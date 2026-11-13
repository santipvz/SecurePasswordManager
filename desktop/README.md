# Desktop app

The native app opens the default vault created by the Python app. It unlocks with the master password and displays entry names, usernames, and websites. Choose **Lock vault** to end the session immediately. The app also locks after five minutes without keyboard or pointer input.

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
