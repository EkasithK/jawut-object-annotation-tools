from __future__ import annotations

import sqlite3
from pathlib import Path

from jawut.db import connection


def test_connect_creates_file_and_parent_dirs(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "project.db"
    conn = connection.connect(db)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    assert db.exists()


def test_connect_is_idempotent_for_same_path(db_path: Path) -> None:
    assert connection.connect(db_path) is connection.connect(db_path)


def test_connect_resolves_equivalent_paths_to_one_connection(tmp_path: Path) -> None:
    direct = tmp_path / "project.db"
    indirect = tmp_path / "sub" / ".." / "project.db"
    (tmp_path / "sub").mkdir()
    assert connection.connect(direct) is connection.connect(indirect)


def test_pragmas_are_applied(db_path: Path) -> None:
    conn = connection.connect(db_path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_row_factory_gives_named_access(db_path: Path) -> None:
    conn = connection.connect(db_path)
    conn.execute("CREATE TABLE t (name TEXT)")
    conn.execute("INSERT INTO t VALUES ('helmet')")
    assert conn.execute("SELECT name FROM t").fetchone()["name"] == "helmet"


def test_close_removes_from_registry(db_path: Path) -> None:
    first = connection.connect(db_path)
    connection.close(db_path)
    assert connection.connect(db_path) is not first


def test_probe_reports_no_project_when_nothing_open() -> None:
    assert connection.probe() == "no project open"


def test_probe_reports_ok_with_a_live_connection(db_path: Path) -> None:
    connection.connect(db_path)
    assert connection.probe() == "ok"


def test_probe_reports_error_on_a_closed_connection(db_path: Path) -> None:
    conn = connection.connect(db_path)
    conn.close()  # closed underneath the registry
    assert connection.probe().startswith("error:")


def test_close_all_closes_every_connection(tmp_path: Path) -> None:
    conns = [connection.connect(tmp_path / f"p{i}.db") for i in range(3)]
    connection.close_all()
    assert connection.probe() == "no project open"
    for conn in conns:
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            continue
        raise AssertionError("connection should have been closed")
