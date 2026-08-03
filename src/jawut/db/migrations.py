"""Schema versioning via ``PRAGMA user_version``.

Version 1 is the base schema in ``schema.sql``. Every later version is a function in
:data:`MIGRATIONS` that upgrades from the previous one. Migrations run inside a single
transaction, so a failure leaves the database at its previous version rather than
half-upgraded.

Adding a migration: append to :data:`MIGRATIONS` with the next integer key and bump
:data:`SCHEMA_VERSION`. Never edit an existing migration — a project database in the
wild has already run it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from jawut.resources import package_file

SCHEMA_VERSION = 1

#: Resolved through the package helper so it is found inside a frozen build too.
SCHEMA_PATH = package_file("db", "schema.sql")

Migration = Callable[[sqlite3.Connection], None]

#: Upgrades keyed by the version they produce. Version 1 comes from ``schema.sql``.
MIGRATIONS: dict[int, Migration] = {}


class SchemaTooNewError(RuntimeError):
    """The database was written by a newer version of the application."""

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"project uses schema v{found} but this version only supports "
            f"v{supported} — update the application to open it"
        )
        self.found = found
        self.supported = supported


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def initialize(conn: sqlite3.Connection) -> None:
    """Create the v1 schema in an empty database."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def migrate(conn: sqlite3.Connection) -> int:
    """Bring ``conn`` up to :data:`SCHEMA_VERSION`, returning the resulting version.

    An empty database is initialized from scratch. A database newer than this build
    raises :class:`SchemaTooNewError` rather than being silently downgraded.
    """
    version = current_version(conn)

    if version == 0:
        initialize(conn)
        return SCHEMA_VERSION

    if version > SCHEMA_VERSION:
        raise SchemaTooNewError(found=version, supported=SCHEMA_VERSION)

    while version < SCHEMA_VERSION:
        target = version + 1
        upgrade = MIGRATIONS.get(target)
        if upgrade is None:
            raise RuntimeError(f"no migration registered for schema v{target}")
        try:
            upgrade(conn)
            conn.execute(f"PRAGMA user_version = {target}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        version = target

    return version
