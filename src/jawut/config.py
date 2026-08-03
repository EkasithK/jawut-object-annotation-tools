"""Application-level settings, stored outside any project.

Nothing is ever written next to the executable — a user may extract the app into
Program Files, which is read-only. Settings live in the per-user application data
directory and hold only what is needed to reopen recent work.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from jawut import __version__

SETTINGS_FILENAME = "settings.json"
MAX_RECENT_PROJECTS = 10


class RecentProject(BaseModel):
    name: str
    path: Path
    opened_at: datetime


class Settings(BaseModel):
    version: str = __version__
    recent_projects: list[RecentProject] = Field(default_factory=list)
    last_import_dir: Path | None = None
    last_export_dir: Path | None = None


def app_data_dir() -> Path:
    """Return the per-user directory for application settings.

    Windows is the shipping target; the other branches keep development on Linux and
    macOS working without special-casing at every call site.
    """
    override = os.environ.get("JAWUT_APP_DATA_DIR")
    if override:
        return Path(override)

    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "Jawut"
        return Path.home() / "AppData" / "Roaming" / "Jawut"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Jawut"

    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "jawut"


def settings_path() -> Path:
    return app_data_dir() / SETTINGS_FILENAME


def default_projects_dir() -> Path:
    """Where the New Project dialog starts. Created lazily, only if the user accepts."""
    documents = Path.home() / "Documents"
    base = documents if documents.is_dir() else Path.home()
    return base / "Jawut Projects"


def load_settings() -> Settings:
    """Read settings, falling back to defaults if the file is missing or corrupt.

    A malformed settings file must never block startup — the worst case is losing the
    recent-projects list, which the user can rebuild by opening a project.
    """
    path = settings_path()
    if not path.is_file():
        return Settings()
    try:
        return Settings.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, json.JSONDecodeError, OSError, UnicodeDecodeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    """Write settings atomically so an interrupted write cannot corrupt the file."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(settings.model_dump_json(indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def remember_project(name: str, project_dir: Path) -> Settings:
    """Move a project to the front of the recent list and persist the change."""
    resolved = project_dir.resolve()
    settings = load_settings()
    remaining = [p for p in settings.recent_projects if p.path.resolve() != resolved]
    settings.recent_projects = [
        RecentProject(name=name, path=resolved, opened_at=datetime.now(UTC)),
        *remaining,
    ][:MAX_RECENT_PROJECTS]
    save_settings(settings)
    return settings


def forget_project(project_dir: Path) -> Settings:
    resolved = project_dir.resolve()
    settings = load_settings()
    settings.recent_projects = [
        p for p in settings.recent_projects if p.path.resolve() != resolved
    ]
    save_settings(settings)
    return settings


def existing_recent_projects() -> list[RecentProject]:
    """Recent entries whose directory still exists.

    Projects get moved and deleted outside the app, so the stored list is a hint
    rather than a fact. Missing entries are hidden but left in the file, since a
    project on a disconnected drive should reappear when it is plugged back in.
    """
    return [p for p in load_settings().recent_projects if p.path.is_dir()]
