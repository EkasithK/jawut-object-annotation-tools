"""The two calls behind "Open existing dataset"."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import MakeImage
from tests.unit.test_dataset import write_labels, write_yaml


def build_dataset(root: Path, make_image: MakeImage) -> Path:
    make_image("a.jpg", folder=root / "images")
    make_image("b.jpg", folder=root / "images")
    write_labels(root / "labels", a="1 0.5 0.5 0.2 0.2\n")
    write_yaml(root / "data.yaml", ["no_helmet", "helmet"])
    return root


def test_scan_reports_what_is_in_the_folder(
    client: TestClient, tmp_path: Path, make_image: MakeImage
) -> None:
    root = build_dataset(tmp_path / "helmet", make_image)

    response = client.post("/api/v1/datasets/scan", json={"path": str(root)})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["layout"] == "images_labels"
    assert data["image_count"] == 2
    assert data["label_count"] == 1
    assert data["class_names"] == ["no_helmet", "helmet"]


def test_scanning_a_missing_folder_is_rejected(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.post(
        "/api/v1/datasets/scan", json={"path": str(tmp_path / "nowhere")}
    )
    assert response.status_code == 422


def test_adopt_creates_the_project_and_opens_it(
    client: TestClient, tmp_path: Path, make_image: MakeImage
) -> None:
    root = build_dataset(tmp_path / "helmet", make_image)

    response = client.post(
        "/api/v1/datasets/adopt",
        json={
            "path": str(root),
            "name": "Helmet Relabel",
            "parent_dir": str(tmp_path / "workspace"),
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["project"]["name"] == "Helmet Relabel"
    assert data["images_imported"] == 2
    assert data["classes_created"] == 2
    assert data["boxes_created"] == 1

    # The project is left open, so the frontend goes straight to the workspace.
    listed = client.get("/api/v1/classes").json()["data"]["classes"]
    named = [c["name"] for c in listed]
    assert named == ["no_helmet", "helmet"]


def test_adopt_remembers_the_project_in_the_recent_list(
    client: TestClient, tmp_path: Path, make_image: MakeImage
) -> None:
    root = build_dataset(tmp_path / "helmet", make_image)

    client.post(
        "/api/v1/datasets/adopt",
        json={
            "path": str(root),
            "name": "Helmet Relabel",
            "parent_dir": str(tmp_path / "workspace"),
        },
    )

    recent = client.get("/api/v1/projects").json()["data"]["recent"]
    assert [entry["name"] for entry in recent] == ["Helmet Relabel"]


def test_adopting_an_empty_folder_is_rejected(
    client: TestClient, tmp_path: Path
) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()

    response = client.post(
        "/api/v1/datasets/adopt",
        json={
            "path": str(empty),
            "name": "Nothing",
            "parent_dir": str(tmp_path / "workspace"),
        },
    )

    assert response.status_code == 422
    assert "no images" in response.json()["error"]["message"]
