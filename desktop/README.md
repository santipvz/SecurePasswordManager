# Desktop app

## Install on Ubuntu

The desktop beta targets Ubuntu 24.04 LTS on amd64. Download the `.deb` and `SHA256SUMS` from [GitHub Releases](https://github.com/santipvz/SecurePasswordManager/releases). Verify the download and install it from the directory containing both files.

```sh
sha256sum --check SHA256SUMS &&
  gh attestation verify secure-password-manager_0.1.1_amd64.deb \
    --repo santipvz/SecurePasswordManager --source-ref refs/heads/main &&
  sudo apt install ./secure-password-manager_0.1.1_amd64.deb
```

Open **Secure Password Manager** from the applications menu as your normal user. The package includes the vault process and its Python runtime. Use `sudo apt remove secure-password-manager` to uninstall. Ubuntu's package manager leaves vaults and backups in your home directory during upgrades and removal. The default vault lives at `${XDG_DATA_HOME:-$HOME/.local/share}/SecurePasswordManager/vault.spm`.

Use a USB YubiKey that supports FIDO2 and the `hmac-secret` extension. Ubuntu's udev and logind grant device access to the active local desktop user for recognized FIDO keys. If the app cannot see the key, reconnect it in the active desktop session and check its USB access using [Yubico's Linux device permissions guide](https://developers.yubico.com/yubikey-manager/Device_Permissions.html). Run the app under your desktop account.

## Use the vault

The native app checks the default vault and can open another `.spm` file or create a new one through the system file dialog. Creating a vault requires a master password of at least 15 characters. An existing file is preserved if you select its name while creating a vault.

If the selected vault has a registered YubiKey, switch to **YubiKey** on the unlock screen, then choose **Unlock with YubiKey**. On Windows, follow the system security prompt. On Linux and macOS, enter the FIDO2 PIN if your key requires one and touch the key when it blinks. You can cancel the attempt or switch back to the master password.

Search an unlocked vault by name, username, or website. Press **Ctrl+K** or **Command+K** to focus search. Use the arrow keys to move through results and **Enter** to open one. Select an entry to view its details, edit it, or delete it after confirmation. Leave the password field blank when editing to keep the saved password.

Passwords stay hidden until you reveal them. A reveal lasts 10 seconds and ends when you leave the details view or the window loses focus. Copy from a search result or the credential details. Rust sends the password directly to the system clipboard and attempts to clear it after 30 seconds or when the vault locks, provided it still contains the copied value.

Open **Generator** from the top navigation or **Password generator** from the lock screen. In the credential editor, choose **Open password generator** and **Use password** to fill the password field. The generator supports 12 to 256 characters and optional symbols.

Choose **Review** to check the unlocked vault for short and exactly reused passwords. Select a result to open the corresponding credential. The review runs locally and leaves the vault file unchanged.

Open **Settings** to save an encrypted backup or open an existing backup as a separate vault. A backup keeps the unlock methods from the moment it was saved. You can also import up to 64 legacy `.key` files at a time. The import saves the whole batch together and leaves the original plaintext files on disk.

Use **Settings** to register or remove a YubiKey with the current master password. Changing the master password rotates the active vault key and removes the active YubiKey registration. You can then register a key again. Keep the previous unlock method if you need to open an older backup.

Choose **Lock vault** to end the session immediately. The app also locks after five minutes without keyboard or pointer input. On Ubuntu the app uses logind's delay inhibitor to lock before system sleep and checks for elapsed suspend time when logind is unavailable.

## Develop

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

From this directory, run `npm run dev` and open [the desktop interface preview](http://127.0.0.1:1420/preview/). Unlock the fictional vault with `preview-password` or choose **YubiKey** and use the demo PIN `123456`. The preview renders the Tauri interface with in-memory data and simulated commands. Reloading restores the examples. The separate browser demo is at [the root URL](http://127.0.0.1:1420/).

`npm run check` checks Svelte and TypeScript, and `npm run build` bundles the local frontend assets. Run `cargo test --locked --features custom-protocol --manifest-path src-tauri/Cargo.toml` after building both the vault process and frontend to test the bridge. See the [visual system](DESIGN.md) for review scenarios and interface conventions.

## Reproduce the Ubuntu package

On Ubuntu 24.04 amd64, install the build prerequisites and run the locked setup through the vault bundling command above. Then run these commands from the repository root.

```sh
npm ci --prefix desktop
npm run build --prefix desktop
cargo build --release --locked --features custom-protocol --manifest-path desktop/src-tauri/Cargo.toml
uv run --no-sync python desktop/scripts/bundle_notices.py
npm --prefix desktop run tauri -- bundle --config src-tauri/tauri.ubuntu.conf.json \
  --features custom-protocol --bundles deb --ci --no-sign
```

The unsigned test package is in `desktop/src-tauri/target/release/bundle/deb/` and is available as the `ubuntu-24.04-amd64-deb` artifact from the Desktop workflow. The workflow installs it in a clean Ubuntu 24.04 container, opens its application menu entry as a standard user, and checks that an upgrade and purge preserve the synthetic vault and its encrypted backup. Test a physical YubiKey in a local Ubuntu desktop session with a disposable vault by registering the key, locking, and unlocking again with the key.
