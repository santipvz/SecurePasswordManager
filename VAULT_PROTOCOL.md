# Desktop vault protocol

Launch the bundled `cpass-vault-process` executable with private stdin and stdout pipes. For development, run `python -m spm.vault_protocol` using the installed Python package. Supply credentials only through requests. Stdout carries responses, and diagnostics go to stderr.

Requests are UTF-8 JSON objects on separate lines. The maximum request size is 64 KiB including the newline. Every request contains `version: 1`, an integer `id` between 0 and 2⁵³ − 1, and an `operation` string. The response contains `version`, the same `id`, and either a `result` or an `error` with a stable `code` and a user-facing `message`. Invalid requests without a valid ID return `id: null`. An oversized frame returns `request_too_large` and closes the connection.

| Operation | Fields | Result |
| --- | --- | --- |
| `status` | Optional absolute `path` | `exists`, `unlocked`, and `has_security_key` booleans for that path. The FIDO2 indicator is based on the file header before authentication. |
| `open` | `master` password and optional absolute `path` | `unlocked: true` and `has_security_key` after authenticating either existing vault format with its master password. |
| `open_key` | Optional absolute `path`, optional FIDO2 `pin` on Linux and macOS, and optional hexadecimal parent `window` handle on Windows | `unlocked: true` and `has_security_key: true` after authenticating the registered FIDO2 credential. Windows obtains the PIN through its system prompt. |
| `create` | Absolute `path` and `master` password | `unlocked: true` and `has_security_key: false` after creating and opening a new encrypted vault. An existing file is preserved. |
| `generate` | Integer `length` between 12 and 256, boolean `symbols` | A freshly generated `password`. Works without unlocking a vault. |
| `review` | None | `total`, `minimum_length`, `short` credential names, and `reused` groups of credential names. Requires an unlocked session and leaves the vault unchanged. |
| `list` | Optional `query` string | `entries` containing only `name`, `username`, and `url`. Requires an unlocked session. |
| `entry_notes` | Credential `name` | Only the requested credential's `notes`. |
| `entry_password` | Credential `name` | Only the requested credential's `password`. Rust consumes the value locally for clipboard requests. |
| `save_entry` | `name`, optional `username`, `url` and `notes`, optional `previous` name and `password` | Metadata of the saved credential. Omit `previous` to create. On edits, omit `password` to preserve it. |
| `delete_entry` | Credential `name` | `deleted: true` after saving the deletion. |
| `lock` | None | `unlocked: false`. Drops the current session. |

Omit the path to use the platform's default vault path. Opening a vault discards the previous session before attempting authentication. EOF signals cancellation of any pending FIDO2 operation, ends the process, and releases the session. The caller discards replies from cancelled sessions and terminates the process if it fails to exit within the cancellation grace period. Only one request is processed at a time. Keep request and response bodies out of logs.

Credential commands require an unlocked session. Writes use the same conflict-checked encrypted storage as the CLI. List and write replies contain no passwords or notes.
