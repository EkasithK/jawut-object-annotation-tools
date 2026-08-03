"""Small shared helpers for identifiers, timestamps and ordering."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

_DIGITS = re.compile(r"(\d+)")


def new_id() -> str:
    return str(uuid4())


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def natural_sort_key(name: str) -> str:
    """Build a sortable string that orders ``img9`` before ``img10``.

    Plain lexicographic ordering puts ``img10`` first, which makes an image list
    feel shuffled to anyone stepping through it with the arrow keys. Each digit run
    is zero-padded to a fixed width so ordinary text comparison — including
    SQLite's, which is where this value is used — gets it right.
    """
    return "".join(
        part.rjust(12, "0") if part.isdigit() else part.lower()
        for part in _DIGITS.split(name)
    )
