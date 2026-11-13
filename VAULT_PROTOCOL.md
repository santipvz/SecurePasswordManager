# Desktop vault protocol

Launch the bundled `cpass-vault-process` executable with private stdin and stdout pipes. For development, run `python -m spm.vault_protocol` using the installed Python package. Supply credentials only through requests. Stdout carries responses, and diagnostics go to stderr.

Requests are UTF-8 JSON objects on separate lines. The maximum request size is 64 KiB including the newline. Every request contains `version: 1`, an integer `id` between 0 and 2⁵³ − 1, and an `operation` string. The response contains `version`, the same `id`, and either a `result` or an `error` with a stable `code` and a user-facing `message`. Invalid requests without a valid ID return `id: null`. An oversized frame returns `request_too_large` and closes the connection.

| Operation | Fields | Result |
| --- | --- | --- |
| `status` | Optional absolute `path` | `exists`, `unlocked`, and `has_security_key` booleans for that path. The FIDO2 indicator is based on the file header before authentication. |
| `open` | `master` password and optional absolute `path` | `unlocked: true` and `has_security_key` after authenticating either existing vault format with its master password. |
| `list` | Optional `query` string | `entries` containing only `name`, `username`, and `url`. Requires an unlocked session. |
| `lock` | None | `unlocked: false`. Drops the current session. |

Omit the path to use the platform's default vault path. Opening a vault discards the previous session before attempting authentication. EOF ends the process and releases the session. Only one request is processed at a time. Keep request and response bodies out of logs. FIDO2 device interaction is part of the desktop unlock integration.
