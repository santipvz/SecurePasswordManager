# CI and release checks

GitHub Actions runs the Python suite on Linux, Windows, and macOS. The desktop workflow checks Svelte and TypeScript, builds the frontend, packages the Python core, and tests the Rust bridge using synthetic vaults. The Ubuntu job also measures the optimized desktop build. Workflow jobs use read-only repository access.

## Reproduce checks

Use uv 0.13.8, Python 3.12, Node.js 22, and stable Rust. Install the native dependencies in the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/). Run from the repository root.

```sh
uv sync --locked --no-install-project --extra yubikey --group build --group desktop-build --group lint
uv sync --locked --no-build-isolation-package sec-pass-manager --extra yubikey --group build --group desktop-build --group lint
uv run --no-sync python -m unittest discover -s tests -v
uv run --no-sync pylint src/spm
uv run --no-sync python desktop/scripts/bundle_vault.py
npm ci --prefix desktop
npm run check --prefix desktop
npm run build --prefix desktop
cargo test --locked --features custom-protocol --manifest-path desktop/src-tauri/Cargo.toml
```

The first sync installs the locked build backend. The second uses it to build the local project. Commit dependency changes with their corresponding lockfiles. Use `uv lock --upgrade-package <package>` for a targeted Python update. Cargo verifies `Cargo.lock` with `--locked`, and npm verifies `package-lock.json` with `npm ci`.

With [OSV-Scanner v2.7.1](https://github.com/google/osv-scanner/releases/tag/v2.7.1) and [Gitleaks v8.30.1](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1) on your PATH, run these commands. The workflows verify downloaded binaries against pinned checksums.

```sh
bash scripts/scan-dependencies.sh /tmp/spm-dependencies.json
scan_config=$(mktemp -d)
printf '[extend]\nuseDefault = true\n' > "$scan_config/gitleaks.toml"
gitleaks git --redact --no-banner --log-opts='--diff-merges=first-parent HEAD' --config "$scan_config/gitleaks.toml" \
  --gitleaks-ignore-path "$scan_config" --ignore-gitleaks-allow
```

## Review advisories and release

Use the [threat model](THREAT_MODEL.md) for changes to secret handling, IPC, storage, or hardware access. Link test evidence for the relevant boundary in the PR. Use [private vulnerability reporting](SECURITY.md) for suspected vulnerabilities in the app.

Review the dependency report and verify which versions and platforms each finding affects. Record the upstream reference, affected dependency path, and remediation or tracking decision in the release review. Resolve applicable high and critical findings before release. The dependency job fails for advisory groups with CVSS 7.0 or above or an explicit high or critical severity. Review unscored advisories and report their disposition in the release review. For a confirmed secret, revoke or rotate it and investigate its exposure before release.

Require the Python and desktop test evidence, the dependency report, and the secret scan for the release PR into `main`. Confirm the results apply to the release candidate before tagging it. Review new findings from the scheduled scan on `develop` against any published packages they affect.

## Measure the desktop on Ubuntu

Install `webkit2gtk-driver`, `xvfb`, `xauth`, and `dbus-daemon` alongside the normal desktop build prerequisites. Build the frontend and bundled Python core first, then run the optimized build under a virtual X11 display with its own D-Bus session and software rendering.

```sh
cargo build --release --locked --features custom-protocol --manifest-path desktop/src-tauri/Cargo.toml
GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 \
  xvfb-run -a -e /dev/stderr dbus-run-session -- uv run --no-sync python scripts/benchmark_desktop.py \
  desktop/src-tauri/target/release/secure-password-manager-desktop /tmp/desktop-performance.json
```

The benchmark starts the native app three times with a temporary, encrypted vault of 10,000 synthetic credentials. Startup measures WebDriver's launch request until the master password field appears. Search measures input to rendered results for 30 queries. It includes the rendering frame interval. Memory is the combined proportional set size of the unlocked app, WebKit subprocesses, and vault process. The Argon2id measurement calls the vault's existing derivation function five times.

Compare the `desktop-performance` artifacts from the PR and `develop`. Use comparable OS, CPU, and WebKitGTK versions and repeat a run to confirm an apparent regression. The workflow records measurements without imposing fixed timing thresholds on shared runners.
