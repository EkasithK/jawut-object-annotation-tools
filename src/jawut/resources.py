"""Locating files that ship alongside the code.

Only ``.py`` files end up inside a PyInstaller archive; anything else — the SQL
schema, the built frontend — is copied out to a temporary directory whose path is
``sys._MEIPASS``. Every non-Python file the application reads at runtime must be
resolved through :func:`package_file`, and must also be listed in the ``datas``
section of ``packaging/jawut.spec``. Missing either half produces a build that
works from source and fails only once packaged.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def package_file(*parts: str) -> Path:
    """Resolve a path relative to the ``jawut`` package, frozen or not.

    ``package_file("db", "schema.sql")`` finds the schema in a source checkout and
    in a packaged application alike.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    root = Path(bundle) / "jawut" if bundle else Path(__file__).resolve().parent
    return root.joinpath(*parts)
