# Hexagonal architecture

The vault core is shared by the command-line and desktop applications. Dependencies point inward from adapters to application ports and use cases, then to domain types and rules.

| Layer | Responsibilities |
| --- | --- |
| Domain | Credentials, vault state, and pure rules such as identifying password reuse. |
| Application | Use cases for opening, locking, and updating a vault. Defines the ports for storage, encryption, and security keys where those services are needed. |
| Inbound adapters | The CLI and the Python process that accepts desktop requests over private pipes. Both call application use cases. |
| Outbound adapters | The `.spm` codec and filesystem storage, Argon2id and AES-GCM, and the FIDO2 device implementation. They implement the ports defined by the application. |
| Entry points | Construct the adapters and wire them to the application. |

Svelte and TypeScript present the desktop UI. Rust and Tauri manage native dialogs, clipboard operations, and the bundled Python process. Python owns the vault session and uses the same application code for the CLI and desktop. The frontend sends requests through the Rust bridge to the Python adapter.

Move existing code into these boundaries in small, testable changes. Add interfaces at boundaries with a concrete adapter or substitution need. Test domain rules and use cases independently from hardware and UI. Use integration tests for `.spm` compatibility, atomic writes, the desktop protocol, and security-key behavior.
