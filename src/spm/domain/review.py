"""Review credential lengths and exact password reuse in memory."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .credentials import Entry

MIN_REVIEW_LENGTH = 15


@dataclass(frozen=True)
class VaultReview:
    """Findings identified by credential name."""

    total: int
    short: tuple[str, ...]
    reused: tuple[tuple[str, ...], ...]


def review_credentials(entries: Iterable[Entry]) -> VaultReview:
    """Check length and group accounts that share the exact same password."""
    names_by_password = defaultdict(list)
    short = []
    total = 0
    for entry in entries:
        total += 1
        if len(entry.password) < MIN_REVIEW_LENGTH:
            short.append(entry.name)
        names_by_password[entry.password].append(entry.name)
    reused = tuple(tuple(names) for names in names_by_password.values() if len(names) > 1)
    return VaultReview(total, tuple(short), reused)
