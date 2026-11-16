"""Secure random password generation."""

import secrets
import string

DEFAULT_LENGTH = 24
MIN_LENGTH = 12
MAX_LENGTH = 256
SYMBOLS = "!#$%&()*+,-./:;<=>?@[]^_{|}~"


def generate_password(length: int = DEFAULT_LENGTH, *, symbols: bool = True) -> str:
    """Draw uniformly from passwords containing every enabled character class."""
    if not isinstance(length, int) or not MIN_LENGTH <= length <= MAX_LENGTH:
        raise ValueError(f"Length must be between {MIN_LENGTH} and {MAX_LENGTH}.")
    groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
    if symbols:
        groups.append(SYMBOLS)
    alphabet = "".join(groups)
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if all(any(character in group for character in password) for group in groups):
            return password


class PasswordManager:
    """Compatibility entry point for password generation."""

    generate_password = staticmethod(generate_password)
