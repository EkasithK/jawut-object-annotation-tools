"""The currently open project.

The application is single-user and opens one project at a time, so the open project
is process state rather than something threaded through every request. Routers reach
it through :func:`require_project` and :func:`require_connection`, which raise
:class:`NoProjectOpenError` when the welcome screen is still showing.
"""

from __future__ import annotations

import sqlite3
import threading

from jawut.db import connection
from jawut.services.projects import Project

_current: Project | None = None
_lock = threading.Lock()


class NoProjectOpenError(RuntimeError):
    """An operation needing a project was attempted before one was opened."""

    def __init__(self) -> None:
        super().__init__("no project is open")


def set_current(project: Project) -> None:
    """Make ``project`` current, closing any project already open."""
    global _current
    with _lock:
        previous = _current
        _current = project
    if previous is not None and previous.db_path != project.db_path:
        connection.close(previous.db_path)


def current() -> Project | None:
    with _lock:
        return _current


def require_project() -> Project:
    project = current()
    if project is None:
        raise NoProjectOpenError
    return project


def require_connection() -> sqlite3.Connection:
    return connection.connect(require_project().db_path)


def clear() -> None:
    """Close the open project, if any, and return to the welcome state."""
    global _current
    with _lock:
        previous = _current
        _current = None
    if previous is not None:
        connection.close(previous.db_path)
