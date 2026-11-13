"""Command-line interface for the local password manager."""

import argparse
import getpass
import sys
import unicodedata
import warnings
from dataclasses import replace
from pathlib import Path

from .sec_pass_manager import DEFAULT_LENGTH, MAX_LENGTH, MIN_LENGTH, generate_password
from .security_key import open_security_key
from .vault import Entry, Vault, VaultError, default_vault_path, read_legacy
from .domain.review import MIN_REVIEW_LENGTH, review_credentials

ACCESS_SETTINGS = {"key-add", "key-remove", "change-master"}


def _secret(prompt: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning as error:
            raise VaultError(
                "Use a terminal that can hide password input."
            ) from error


def _new_master() -> str:
    master = _secret("New master password: ")
    if master != _secret("Confirm the master password: "):
        raise VaultError("The master passwords do not match.")
    return master


def _visible(value: str) -> str:
    return "".join(
        repr(character)[1:-1] if unicodedata.category(character).startswith("C") else character
        for character in value
    )


def _generator_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--length", "-l", type=int, default=DEFAULT_LENGTH,
        help=f"length from {MIN_LENGTH} to {MAX_LENGTH} (default: {DEFAULT_LENGTH})",
    )
    parser.add_argument("--no-symbols", action="store_true", help="use letters and numbers only")


def _entry_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="credential name")
    parser.add_argument("--username", "-u", help="username or email")
    parser.add_argument("--url", help="website")
    parser.add_argument("--notes", help="notes visible in the terminal history")
    password = parser.add_mutually_exclusive_group()
    password.add_argument("--generate", action="store_true", help="generate a new password")
    password.add_argument(
        "--prompt-password", action="store_true", help="enter a password without displaying it",
    )
    _generator_options(parser)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and store passwords in a local vault.",
    )
    parser.add_argument(
        "--vault", type=Path, default=default_vault_path(), help="vault path",
    )
    parser.add_argument(
        "--security-key", action="store_true", help="unlock with a registered FIDO2 key",
    )
    actions = parser.add_subparsers(dest="action", metavar="command")
    actions.add_parser("init", help="create a vault")
    _generator_options(actions.add_parser("generate", help="generate a password without saving it"))
    _entry_options(actions.add_parser("add", help="add a credential"))
    edit = actions.add_parser("edit", help="edit a credential")
    _entry_options(edit)
    edit.add_argument("--name", dest="new_name", help="rename the credential")
    listing = actions.add_parser("list", help="list or search credentials")
    listing.add_argument("query", nargs="?", default="")
    actions.add_parser("audit", help="review short and reused passwords")
    show = actions.add_parser("show", help="show credential details")
    show.add_argument("name")
    show.add_argument(
        "--password", action="store_true", help="write the password to standard output",
    )
    delete = actions.add_parser("delete", help="delete a credential")
    delete.add_argument("name")
    delete.add_argument("--yes", "-y", action="store_true", help="confirm deletion")
    import_key = actions.add_parser("import-key", help="import legacy .key files")
    import_key.add_argument("files", nargs="+", type=Path)
    backup = actions.add_parser("backup", help="save an encrypted backup")
    backup.add_argument("destination", type=Path)
    actions.add_parser("change-master", help="change the master password")
    actions.add_parser("key-add", help="register a FIDO2 key")
    actions.add_parser("key-remove", help="remove the FIDO2 key from the vault")
    return parser


def _entry(args: argparse.Namespace, current: Entry | None = None) -> Entry:
    if args.generate:
        password = generate_password(args.length, symbols=not args.no_symbols)
    elif current is None or args.prompt_password:
        password = _secret("Account password: ")
    else:
        password = current.password
    fields = {
        name: getattr(args, name) for name in ("username", "url", "notes")
        if getattr(args, name) is not None
    }
    if current is None:
        return Entry(name=args.name, password=password, **fields)
    name = current.name if args.new_name is None else args.new_name
    return replace(current, name=name, password=password, **fields)


def _show(entry: Entry, reveal: bool) -> None:
    if reveal:
        print(_visible(entry.password) if sys.stdout.isatty() else entry.password)
    else:
        for label, value in (
            ("Name", entry.name), ("Username", entry.username),
            ("Website", entry.url), ("Notes", entry.notes),
        ):
            if value:
                print(f"{label}: {_visible(value)}")


def _audit(vault: Vault) -> None:
    report = review_credentials(vault.list())
    if report.total == 0:
        print("The vault is empty.")
        return
    print(f"Credentials reviewed: {report.total}")
    if report.short:
        print(f"Fewer than {MIN_REVIEW_LENGTH} characters:")
        for name in report.short:
            print(f"  - {_visible(name)}")
    if report.reused:
        print("Reused passwords:")
        for number, group in enumerate(report.reused, start=1):
            print(f"  Group {number}")
            for name in group:
                print(f"    - {_visible(name)}")
    if not report.short and not report.reused:
        print(f"All passwords are unique and at least {MIN_REVIEW_LENGTH} characters long.")


def _hardware():
    pin = None

    def read_pin():
        nonlocal pin
        if pin is None:
            pin = _secret("FIDO2 key PIN: ")
        return pin

    return open_security_key(
        read_pin, lambda message: print(message, file=sys.stderr),
    )


def _manage(vault: Vault, args: argparse.Namespace) -> None:
    match args.action:
        case "add":
            vault.add([_entry(args)])
            print("Credential saved.")
        case "edit":
            current = vault.get(args.name)
            vault.edit(current.name, _entry(args, current))
            print("Credential updated.")
        case "list":
            for entry in vault.list(args.query):
                print(_visible(entry.name))
        case "audit":
            _audit(vault)
        case "show":
            _show(vault.get(args.name), args.password)
        case "delete":
            entry = vault.get(args.name)
            if not args.yes:
                response = input(f"Delete {_visible(entry.name)!r}? [y/N] ")
                if response.strip().casefold() not in {"y", "yes", "s", "sí", "si"}:
                    return
            vault.delete(entry.name)
            print("Credential deleted.")
        case "import-key":
            vault.add(read_legacy(path) for path in args.files)
            print(f"Imported {len(args.files)} credentials. The original files remain on disk.")
        case "backup":
            vault.backup(args.destination)
            print("Encrypted backup saved.")


def _configure_access(vault: Vault, action: str, master: str) -> None:
    match action:
        case "change-master":
            if vault.has_security_key:
                print("Changing the master password removes the FIDO2 key.", file=sys.stderr)
            vault.change_master(_new_master())
            print("Master password updated.")
        case "key-add":
            if vault.has_security_key:
                raise VaultError("A FIDO2 key is already registered. Run cpass key-remove first.")
            with _hardware() as key:
                enrollment = key.enroll()
            vault.add_security_key(master, enrollment)
            print("FIDO2 key registered. Unlock with cpass --security-key.")
        case "key-remove":
            vault.remove_security_key(master)
            print("FIDO2 key removed from the active vault.")


def main(argv: list[str] | None = None) -> int:
    """Run a command and report errors with a nonzero exit status."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.security_key and (args.action == "init" or args.action in ACCESS_SETTINGS):
            raise VaultError("Use the master password to change unlock methods.")
        if args.action is None:
            parser.print_help()
        elif args.action == "generate":
            print(generate_password(args.length, symbols=not args.no_symbols))
        elif args.action == "init":
            Vault.create(args.vault, _new_master())
            print(f"Vault created at {_visible(str(args.vault))}")
        elif args.security_key:
            with _hardware() as key:
                vault = Vault(args.vault, security_key=key)
            _manage(vault, args)
        else:
            master = _secret("Master password: ")
            vault = Vault(args.vault, master)
            if args.action in ACCESS_SETTINGS:
                _configure_access(vault, args.action, master)
            else:
                _manage(vault, args)
    except (VaultError, OSError, ValueError) as error:
        print(f"Error: {_visible(str(error))}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nOperation cancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
