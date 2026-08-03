"""Per-project SQLite connections.

The app has at most one project open at a time, but connections are held in a registry
keyed by database path so that opening a second project cannot silently leak the first.
Connections are created with ``check_same_thread=False`` because uvicorn serves requests
from a thread pool; writes are serialised by SQLite itself under WAL.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_connections: dict[Path, sqlite3.Connection] = {}
_lock = threading.Lock()


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")


def connect(db_path: Path) -> sqlite3.Connection:
    """Return the open connection for ``db_path``, creating it on first use."""
    resolved = db_path.resolve()
    with _lock:
        existing = _connections.get(resolved)
        if existing is not None:
            return existing
        resolved.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(resolved, check_same_thread=False)
        _configure(conn)
        _connections[resolved] = conn
        return conn


def close(db_path: Path) -> None:
    resolved = db_path.resolve()
    with _lock:
        conn = _connections.pop(resolved, None)
    if conn is not None:
        conn.close()


def close_all() -> None:
    """Close every open connection. Called from the FastAPI lifespan shutdown."""
    with _lock:
        conns = list(_connections.values())
        _connections.clear()
    for conn in conns:
        conn.close()


def probe() -> str:
    """Report storage health for ``GET /ready``.

    With no project open there is nothing to check, which is a healthy state — the
    welcome screen is reachable and functional.
    """
    with _lock:
        conns = list(_connections.values())
    if not conns:
        return "no project open"
    try:
        for conn in conns:
            conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        return f"error: {exc}"
    return "ok"
