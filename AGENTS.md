# Repository guidance

- Follow [CONTRIBUTING.md](CONTRIBUTING.md) for branch targets, atomic commits, and pull requests. Use English for code, documentation, issues, and pull requests.
- Preserve the dependency direction described in [ARCHITECTURE.md](ARCHITECTURE.md). Apply these boundaries incrementally as each part of the application is introduced or changed.
- Request Codex review when a pull request is ready. If automatic review is disabled or has yet to start, post `@codex review`. Review the latest changes again after significant fixes. Address actionable findings before squash merging.

## Code Review Rules

- Flag changes that allow the desktop frontend or command-line adapters to bypass vault session checks, expose secrets through logs or process arguments, or persist plaintext credentials outside the vault.
- Flag changes that can make existing `.spm` files or registered FIDO2 credentials unusable. Require compatibility evidence for changes to the format or unlocking flow.
- Flag application or domain code that takes a dependency on a concrete UI, filesystem, cryptography, or device adapter. These dependencies should be composed at the application entry point.
