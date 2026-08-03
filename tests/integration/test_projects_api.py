from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jawut import session
from jawut.db import migrations


@pytest.fixture(autouse=True)
def _isolated_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAWUT_APP_DATA_DIR", str(tmp_path / "appdata"))
    session.clear()
    yield
    session.clear()


def _create(client: TestClient, tmp_path: Path, name: str = "Helmet") -> dict:
    response = client.post(
        "/api/v1/projects", json={"name": name, "parent_dir": str(tmp_path)}
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_welcome_state_is_empty_on_first_run(
    client: TestClient, tmp_path: Path
) -> None:
    data = client.get("/api/v1/projects").json()["data"]
    assert data["open_project"] is None
    assert data["recent"] == []
    assert data["default_projects_dir"].endswith("Jawut Projects")


def test_create_returns_the_new_project(client: TestClient, tmp_path: Path) -> None:
    data = _create(client, tmp_path)
    assert data["name"] == "Helmet"
    assert data["schema_version"] == migrations.SCHEMA_VERSION
    assert (Path(data["path"]) / "project.db").is_file()


def test_create_opens_the_project_and_records_it_as_recent(
    client: TestClient, tmp_path: Path
) -> None:
    _create(client, tmp_path)
    state = client.get("/api/v1/projects").json()["data"]

    assert state["open_project"]["name"] == "Helmet"
    assert [r["name"] for r in state["recent"]] == ["Helmet"]


def test_create_rejects_an_invalid_name(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/v1/projects", json={"name": "bad/name", "parent_dir": str(tmp_path)}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_rejects_a_non_empty_target_directory(
    client: TestClient, tmp_path: Path
) -> None:
    occupied = tmp_path / "Helmet"
    occupied.mkdir()
    (occupied / "photo.jpg").write_bytes(b"")

    response = client.post(
        "/api/v1/projects", json={"name": "Helmet", "parent_dir": str(tmp_path)}
    )
    assert response.status_code == 422
    assert "not empty" in response.json()["error"]["message"]


def test_open_restores_a_closed_project(client: TestClient, tmp_path: Path) -> None:
    created = _create(client, tmp_path)
    client.post("/api/v1/projects/close")

    response = client.post("/api/v1/projects/open", json={"path": created["path"]})
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Helmet"


def test_open_reports_a_missing_project(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/api/v1/projects/open", json={"path": str(tmp_path / "nope")}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_open_reports_a_directory_that_is_not_a_project(
    client: TestClient, tmp_path: Path
) -> None:
    plain = tmp_path / "just-photos"
    plain.mkdir()

    response = client.post("/api/v1/projects/open", json={"path": str(plain)})
    assert response.status_code == 404
    assert "not a project" in response.json()["error"]["message"]


def test_opening_a_second_project_replaces_the_first(
    client: TestClient, tmp_path: Path
) -> None:
    _create(client, tmp_path, "One")
    _create(client, tmp_path, "Two")

    state = client.get("/api/v1/projects").json()["data"]
    assert state["open_project"]["name"] == "Two"
    assert [r["name"] for r in state["recent"]] == ["Two", "One"]


def test_close_returns_to_the_welcome_state(client: TestClient, tmp_path: Path) -> None:
    _create(client, tmp_path)

    data = client.post("/api/v1/projects/close").json()["data"]
    assert data["open_project"] is None
    assert [r["name"] for r in data["recent"]] == ["Helmet"]


def test_forget_removes_a_project_from_recent_but_leaves_it_on_disk(
    client: TestClient, tmp_path: Path
) -> None:
    created = _create(client, tmp_path)

    data = client.post("/api/v1/projects/forget", json={"path": created["path"]}).json()
    assert data["data"]["recent"] == []
    assert (Path(created["path"]) / "project.db").is_file()


def test_a_deleted_project_disappears_from_recent(
    client: TestClient, tmp_path: Path
) -> None:
    import shutil

    created = _create(client, tmp_path)
    client.post("/api/v1/projects/close")
    shutil.rmtree(created["path"])

    assert client.get("/api/v1/projects").json()["data"]["recent"] == []


def test_require_project_raises_when_nothing_is_open() -> None:
    session.clear()
    with pytest.raises(session.NoProjectOpenError):
        session.require_project()


def test_require_connection_gives_a_working_connection(
    client: TestClient, tmp_path: Path
) -> None:
    _create(client, tmp_path)
    conn = session.require_connection()
    assert conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0] == 0
