"""Project lifecycle: create, open, inspect.

A project is a directory, not a file:

    <project>/
        project.db      every annotation, class and status
        images/         imported images, when they are copied rather than linked

Keeping it to a directory means a user can back up or move their work by copying a
folder, which is the only mental model that survives contact with a non-technical
audience.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from jawut import __version__
from jawut.db import connection, migrations

DB_FILENAME = "project.db"
IMAGES_DIRNAME = "images"

#: Characters Windows forbids in a path component, plus the separators.
_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Reserved device names on Windows, which cannot be used as directory names.
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ProjectError(RuntimeError):
    """A project could not be created or opened."""


class Project(BaseModel):
    name: str
    path: Path
    db_path: Path
    images_dir: Path
    schema_version: int
    created_at: datetime


def validate_name(name: str) -> str:
    """Return a cleaned project name, or raise if it cannot be a directory name.

    The name becomes a directory, so it is validated against Windows' rules even on
    other platforms — otherwise a project created during development on Linux would
    be unopenable on the shipping target.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ProjectError("project name cannot be empty")
    if len(cleaned) > 100:
        raise ProjectError("project name cannot be longer than 100 characters")
    if _INVALID_NAME_CHARS.search(cleaned):
        raise ProjectError(r'project name cannot contain < > : " / \ | ? *')
    if cleaned.upper().split(".")[0] in _RESERVED_NAMES:
        raise ProjectError(f"'{cleaned}' is a reserved name on Windows")
    # Trailing spaces are already gone from the strip above; Windows also refuses a
    # trailing period, which nothing else here catches.
    if cleaned.endswith("."):
        raise ProjectError("project name cannot end with a period")
    return cleaned


def db_path_for(project_dir: Path) -> Path:
    return project_dir / DB_FILENAME


def images_dir_for(project_dir: Path) -> Path:
    return project_dir / IMAGES_DIRNAME


def is_project_dir(path: Path) -> bool:
    return db_path_for(path).is_file()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def create(parent_dir: Path, name: str) -> Project:
    """Create a new project directory under ``parent_dir``.

    Refuses to touch an existing non-empty directory, so pointing the dialog at a
    folder full of images cannot scatter project files through it.
    """
    cleaned = validate_name(name)
    project_dir = (parent_dir / cleaned).resolve()

    if project_dir.exists() and any(project_dir.iterdir()):
        raise ProjectError(f"'{project_dir}' already exists and is not empty")

    project_dir.mkdir(parents=True, exist_ok=True)
    images_dir_for(project_dir).mkdir(exist_ok=True)

    db_path = db_path_for(project_dir)
    conn = connection.connect(db_path)
    try:
        migrations.migrate(conn)
        created_at = datetime.now(UTC).isoformat()
        set_meta(conn, "project_name", cleaned)
        set_meta(conn, "created_at", created_at)
        set_meta(conn, "app_version", __version__)
        conn.commit()
    except Exception:
        connection.close(db_path)
        raise

    return _describe(project_dir, conn)


def open_project(project_dir: Path) -> Project:
    """Open an existing project, migrating its schema if needed."""
    resolved = project_dir.resolve()
    db_path = db_path_for(resolved)

    if not resolved.is_dir():
        raise ProjectError(f"'{resolved}' does not exist")
    if not db_path.is_file():
        raise ProjectError(f"'{resolved}' is not a project — no {DB_FILENAME} in it")

    conn = connection.connect(db_path)
    try:
        migrations.migrate(conn)
    except migrations.SchemaTooNewError as exc:
        connection.close(db_path)
        raise ProjectError(str(exc)) from exc
    except Exception:
        connection.close(db_path)
        raise

    # Older projects predate the images directory, and a user may have deleted it.
    images_dir_for(resolved).mkdir(exist_ok=True)
    set_meta(conn, "app_version", __version__)
    conn.commit()

    return _describe(resolved, conn)


def close_project(project_dir: Path) -> None:
    connection.close(db_path_for(project_dir.resolve()))


def _describe(project_dir: Path, conn: sqlite3.Connection) -> Project:
    created_raw = get_meta(conn, "created_at")
    return Project(
        name=get_meta(conn, "project_name") or project_dir.name,
        path=project_dir,
        db_path=db_path_for(project_dir),
        images_dir=images_dir_for(project_dir),
        schema_version=migrations.current_version(conn),
        created_at=(
            datetime.fromisoformat(created_raw) if created_raw else datetime.now(UTC)
        ),
    )
