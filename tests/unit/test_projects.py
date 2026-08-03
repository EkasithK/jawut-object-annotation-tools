from __future__ import annotations

from pathlib import Path

import pytest

from jawut.db import connection, migrations
from jawut.services import projects


def test_create_makes_the_expected_layout(tmp_path: Path) -> None:
    project = projects.create(tmp_path, "Helmet Relabel")

    assert project.path == (tmp_path / "Helmet Relabel").resolve()
    assert project.db_path.is_file()
    assert project.images_dir.is_dir()
    assert project.name == "Helmet Relabel"
    assert project.schema_version == migrations.SCHEMA_VERSION


def test_create_records_metadata(tmp_path: Path) -> None:
    project = projects.create(tmp_path, "Helmet Relabel")
    conn = connection.connect(project.db_path)

    assert projects.get_meta(conn, "project_name") == "Helmet Relabel"
    assert projects.get_meta(conn, "created_at")
    assert projects.get_meta(conn, "app_version")


def test_create_trims_surrounding_whitespace(tmp_path: Path) -> None:
    assert projects.create(tmp_path, "  Padded  ").name == "Padded"


def test_create_refuses_a_non_empty_directory(tmp_path: Path) -> None:
    occupied = tmp_path / "Existing"
    occupied.mkdir()
    (occupied / "photo.jpg").write_bytes(b"")

    with pytest.raises(projects.ProjectError, match="not empty"):
        projects.create(tmp_path, "Existing")


def test_create_accepts_an_existing_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "Empty").mkdir()
    assert projects.create(tmp_path, "Empty").db_path.is_file()


@pytest.mark.parametrize(
    "name",
    ["", "   ", "bad/name", "bad\\name", "has:colon", "star*", 'quote"here', "q?mark"],
)
def test_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(projects.ProjectError):
        projects.validate_name(name)


@pytest.mark.parametrize("name", ["CON", "con", "NUL", "COM1", "LPT9", "aux.txt"])
def test_windows_reserved_names_are_rejected(name: str) -> None:
    with pytest.raises(projects.ProjectError, match="reserved"):
        projects.validate_name(name)


def test_a_trailing_period_is_rejected() -> None:
    with pytest.raises(projects.ProjectError, match="end with a period"):
        projects.validate_name("trailing.")


def test_a_trailing_space_is_stripped_rather_than_rejected() -> None:
    assert projects.validate_name("Helmet ") == "Helmet"


def test_overlong_names_are_rejected() -> None:
    with pytest.raises(projects.ProjectError, match="100 characters"):
        projects.validate_name("x" * 101)


def test_open_returns_the_same_project(tmp_path: Path) -> None:
    created = projects.create(tmp_path, "Helmet")
    projects.close_project(created.path)

    reopened = projects.open_project(created.path)
    assert reopened.name == "Helmet"
    assert reopened.created_at == created.created_at


def test_open_rejects_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(projects.ProjectError, match="does not exist"):
        projects.open_project(tmp_path / "nope")


def test_open_rejects_a_directory_that_is_not_a_project(tmp_path: Path) -> None:
    plain = tmp_path / "just-photos"
    plain.mkdir()

    with pytest.raises(projects.ProjectError, match="not a project"):
        projects.open_project(plain)


def test_open_recreates_a_deleted_images_directory(tmp_path: Path) -> None:
    project = projects.create(tmp_path, "Helmet")
    projects.close_project(project.path)
    project.images_dir.rmdir()

    assert projects.open_project(project.path).images_dir.is_dir()


def test_open_refuses_a_project_from_a_newer_build(tmp_path: Path) -> None:
    project = projects.create(tmp_path, "Helmet")
    conn = connection.connect(project.db_path)
    conn.execute(f"PRAGMA user_version = {migrations.SCHEMA_VERSION + 1}")
    conn.commit()
    projects.close_project(project.path)

    with pytest.raises(projects.ProjectError, match="update the application"):
        projects.open_project(project.path)


def test_is_project_dir_detects_a_project(tmp_path: Path) -> None:
    project = projects.create(tmp_path, "Helmet")
    assert projects.is_project_dir(project.path)
    assert not projects.is_project_dir(tmp_path)


def test_set_meta_overwrites_an_existing_key(tmp_path: Path) -> None:
    project = projects.create(tmp_path, "Helmet")
    conn = connection.connect(project.db_path)

    projects.set_meta(conn, "project_name", "Renamed")
    conn.commit()
    assert projects.get_meta(conn, "project_name") == "Renamed"


def test_get_meta_returns_none_for_an_unknown_key(tmp_path: Path) -> None:
    project = projects.create(tmp_path, "Helmet")
    conn = connection.connect(project.db_path)
    assert projects.get_meta(conn, "nothing_here") is None


def test_two_projects_can_be_open_at_once(tmp_path: Path) -> None:
    one = projects.create(tmp_path, "One")
    two = projects.create(tmp_path, "Two")

    assert connection.connect(one.db_path) is not connection.connect(two.db_path)
