# Desktop threat model

This document describes the intended security boundaries for the Tauri desktop app. Use it when reviewing changes to the desktop bridge, the vault session, and the release process.

## Assets and trust boundaries

The master password, security-key PIN, FIDO2 PRF output, vault encryption key, passwords, and notes are sensitive. Credential names, usernames, and URLs can also reveal private information. The desktop app operates offline, with the vault stored in the user's application data directory or at a path selected by the user.

| Boundary | Data and controls |
| --- | --- |
| Svelte WebView → Rust | Tauri loads bundled assets. Grant explicitly listed commands to the main window, keep a restrictive content security policy, and keep untrusted links in the system browser. The WebView accepts the master password and, on platforms that need app-provided PIN entry, the PIN. Clear the input fields after submission. An unlocked view receives metadata and only the secrets needed for an explicit action such as editing or revealing a credential. |
| Rust → Python | Rust launches the bundled executable by its trusted path with private stdin and stdout pipes. The versioned protocol validates operation names, types, lengths, and request IDs. Route diagnostics separately with sensitive fields omitted. The master password and PIN travel in memory for the operation that needs them. |
| Python → vault file | Python owns the decrypted session and the data key. The codec authenticates the encrypted header and payload. The filesystem adapter performs conflict-checked replacement and prevents overwriting existing backup destinations. Both existing vault formats and registered FIDO2 credentials need compatibility tests. |
| Python → FIDO2 | The authenticator verifies the PIN or fingerprint and produces the PRF output. A platform-managed PIN prompt can keep the PIN outside the app. Bind authentication to the registered credential and verify user presence, user verification, and the signature. The master password remains a recovery method. |
| Rust → system clipboard | Copy an explicitly requested password through Rust. Attempt to remove it on lock or after 30 seconds if the clipboard still holds that copy. Other applications, clipboard synchronization, and clipboard history may retain the value. |

## Threats and handling

- **Vault theft or tampering.** Argon2id slows offline guessing, and AES-GCM detects modified ciphertext and headers. Master password strength still matters, including when FIDO2 is enabled. An older, valid copy can be substituted for the current file. Encryption alone gives no guarantee that a snapshot is the latest.
- **Malformed input.** Bound messages before decoding them and validate vault lengths and version headers. Use explicit allowlists for operations, avoid arbitrary shell execution, and enforce session checks in Python. Render user-controlled content as text and validate link schemes before handing URLs to the OS.
- **Stale writes and interrupted operations.** Validate the snapshot before replacing it and report conflicts. An IPC failure may leave the result of a write unknown. Reopen and inspect the vault before retrying a mutation.
- **Lock, cancellation, and process failure.** Rust invalidates outstanding requests and discards responses from a previous session. The Python process releases the unlocked session and closes on EOF. Rust terminates it if a lock or shutdown cannot be confirmed. Clear any revealed values and session state in the WebView on lock. Windows may handle cancellation through a native device prompt. In-memory cleanup reduces the time secrets are reachable. Python, Rust, and the WebView can leave transient copies.
- **Compromised local environment.** Malware running as the user or administrator can capture keystrokes, inspect memory, or read the clipboard. The vault and FIDO2 do not provide isolation from a compromised OS. Old backups retain their original unlock methods.

## Release evidence

Review changes to the WebView permissions, protocol, filesystem, cryptography, and FIDO2 boundaries against this model. Include test evidence for malformed input, invalid and cancelled authentication, session invalidation, interrupted writes, both supported vault formats, and recovery from backup. Verify installer signatures where applicable and run a physical security-key smoke test on each platform before advertising support. Review dependency advisories, resolve applicable high and critical findings before release, and record remaining risks in the release review.

See [SECURITY.md](SECURITY.md) for private reporting. [Tauri capabilities](https://v2.tauri.app/security/capabilities/) · [NIST SSDF](https://csrc.nist.gov/pubs/sp/800/218/final)
