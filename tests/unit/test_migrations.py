from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jawut.db import connection, migrations


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(row["name"]) for row in rows}


def test_empty_database_is_initialized_to_current_version(db_path: Path) -> None:
    conn = connection.connect(db_path)
    assert migrations.migrate(conn) == migrations.SCHEMA_VERSION
    assert migrations.current_version(conn) == migrations.SCHEMA_VERSION


def test_initialize_creates_every_table(db_path: Path) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    assert {"meta", "classes", "images", "annotations", "edit_log"} <= _tables(conn)


def test_migrate_is_idempotent(db_path: Path) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    conn.execute("INSERT INTO meta (key, value) VALUES ('project_name', 'helmet')")
    conn.commit()

    assert migrations.migrate(conn) == migrations.SCHEMA_VERSION
    row = conn.execute("SELECT value FROM meta WHERE key = 'project_name'").fetchone()
    assert row["value"] == "helmet"


def test_a_newer_schema_is_refused_rather_than_downgraded(db_path: Path) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    conn.execute(f"PRAGMA user_version = {migrations.SCHEMA_VERSION + 5}")

    with pytest.raises(migrations.SchemaTooNewError) as excinfo:
        migrations.migrate(conn)
    assert excinfo.value.found == migrations.SCHEMA_VERSION + 5
    assert excinfo.value.supported == migrations.SCHEMA_VERSION


def test_a_missing_migration_is_an_error(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", migrations.SCHEMA_VERSION + 1)

    with pytest.raises(RuntimeError, match="no migration registered"):
        migrations.migrate(conn)


def test_a_failing_migration_leaves_the_version_untouched(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    start = migrations.current_version(conn)

    def boom(_: sqlite3.Connection) -> None:
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(migrations, "SCHEMA_VERSION", start + 1)
    monkeypatch.setitem(migrations.MIGRATIONS, start + 1, boom)

    with pytest.raises(sqlite3.OperationalError):
        migrations.migrate(conn)
    assert migrations.current_version(conn) == start


def test_foreign_keys_cascade_from_images_to_annotations(db_path: Path) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    conn.execute(
        "INSERT INTO classes (id, name, color, order_index, created_at) "
        "VALUES ('c1', 'Helmet', '#4c8dff', 0, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO images (id, filename, stored_path, is_managed, width, height, "
        "sha256, status, sort_key, created_at, updated_at) VALUES "
        "('i1', 'a.jpg', 'images/a.jpg', 1, 640, 480, 'abc', 'in_progress', 'a.jpg', "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO annotations (id, image_id, class_id, cx, cy, w, h, created_at, "
        "updated_at) VALUES ('a1', 'i1', 'c1', 0.5, 0.5, 0.2, 0.2, "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.commit()

    conn.execute("DELETE FROM images WHERE id = 'i1'")
    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 0


def test_deleting_a_class_in_use_is_blocked_by_the_foreign_key(db_path: Path) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    conn.execute(
        "INSERT INTO classes (id, name, color, order_index, created_at) "
        "VALUES ('c1', 'Helmet', '#4c8dff', 0, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO images (id, filename, stored_path, is_managed, width, height, "
        "sha256, status, sort_key, created_at, updated_at) VALUES "
        "('i1', 'a.jpg', 'images/a.jpg', 1, 640, 480, 'abc', 'in_progress', 'a.jpg', "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO annotations (id, image_id, class_id, cx, cy, w, h, created_at, "
        "updated_at) VALUES ('a1', 'i1', 'c1', 0.5, 0.5, 0.2, 0.2, "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM classes WHERE id = 'c1'")


def test_class_names_are_unique_only_among_live_classes(db_path: Path) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    conn.execute(
        "INSERT INTO classes (id, name, color, order_index, created_at, deleted_at) "
        "VALUES ('c1', 'Ngob', '#4c8dff', 0, '2026-01-01T00:00:00Z', "
        "'2026-01-02T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO classes (id, name, color, order_index, created_at) "
        "VALUES ('c2', 'Ngob', '#3fa96a', 1, '2026-01-03T00:00:00Z')"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO classes (id, name, color, order_index, created_at) "
            "VALUES ('c3', 'Ngob', '#d9564a', 2, '2026-01-04T00:00:00Z')"
        )


@pytest.mark.parametrize(
    ("column", "value"),
    [("cx", -0.1), ("cx", 1.5), ("cy", 2.0), ("w", 0.0), ("h", -1.0), ("w", 1.2)],
)
def test_out_of_range_box_coordinates_are_rejected(
    db_path: Path, column: str, value: float
) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    conn.execute(
        "INSERT INTO classes (id, name, color, order_index, created_at) "
        "VALUES ('c1', 'Helmet', '#4c8dff', 0, '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO images (id, filename, stored_path, is_managed, width, height, "
        "sha256, status, sort_key, created_at, updated_at) VALUES "
        "('i1', 'a.jpg', 'images/a.jpg', 1, 640, 480, 'abc', 'in_progress', 'a.jpg', "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    box = {"cx": 0.5, "cy": 0.5, "w": 0.2, "h": 0.2}
    box[column] = value

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO annotations (id, image_id, class_id, cx, cy, w, h, "
            "created_at, updated_at) VALUES ('a1', 'i1', 'c1', :cx, :cy, :w, :h, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            box,
        )


def test_image_status_is_constrained_to_known_values(db_path: Path) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO images (id, filename, stored_path, is_managed, width, "
            "height, sha256, status, sort_key, created_at, updated_at) VALUES "
            "('i1', 'a.jpg', 'images/a.jpg', 1, 640, 480, 'abc', 'finished', 'a.jpg', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )


def test_duplicate_image_hashes_are_rejected(db_path: Path) -> None:
    conn = connection.connect(db_path)
    migrations.migrate(conn)
    insert = (
        "INSERT INTO images (id, filename, stored_path, is_managed, width, height, "
        "sha256, status, sort_key, created_at, updated_at) VALUES "
        "(?, ?, ?, 1, 640, 480, 'samehash', 'unlabeled', ?, "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.execute(insert, ("i1", "a.jpg", "images/a.jpg", "a.jpg"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, ("i2", "b.jpg", "images/b.jpg", "b.jpg"))
