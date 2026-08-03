from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.conftest import MakeImage

from jawut import session
from jawut.services.projects import Project


@pytest.fixture
def opened(client: TestClient, tmp_path: Path) -> Project:
    """A project created through the API, so the session is wired as in real use."""
    response = client.post(
        "/api/v1/projects",
        json={"name": "Helmet", "parent_dir": str(tmp_path / "workspace")},
    )
    assert response.status_code == 201, response.text
    return session.require_project()


def _import(client: TestClient, source: Path, **kwargs: object) -> dict:
    response = client.post(
        "/api/v1/images/import", json={"source": str(source), **kwargs}
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _make_class(client: TestClient, name: str) -> dict:
    response = client.post("/api/v1/classes", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_calls_without_a_project_are_refused(client: TestClient) -> None:
    session.clear()
    response = client.get("/api/v1/classes")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_PROJECT_OPEN"


def test_import_then_list(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    make_image("b.jpg")

    result = _import(client, tmp_path / "source")
    assert result["imported"] == 2

    listed = client.get("/api/v1/images").json()["data"]
    assert len(listed["images"]) == 2
    assert listed["counts"] == {
        "unlabeled": 2,
        "in_progress": 0,
        "done": 0,
        "needs_review": 0,
        "total": 2,
    }


def test_import_reports_skipped_files(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("good.jpg")
    (tmp_path / "source" / "bad.jpg").write_bytes(b"nonsense")

    result = _import(client, tmp_path / "source")
    assert result["imported"] == 1
    assert len(result["skipped"]) == 1


def test_import_rejects_a_missing_folder(
    client: TestClient, opened: Project, tmp_path: Path
) -> None:
    response = client.post(
        "/api/v1/images/import", json={"source": str(tmp_path / "nowhere")}
    )
    assert response.status_code == 422
    assert "not a folder" in response.json()["error"]["message"]


def test_image_bytes_are_served(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    _import(client, tmp_path / "source")
    image_id = client.get("/api/v1/images").json()["data"]["images"][0]["id"]

    response = client.get(f"/api/v1/images/{image_id}/file")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_a_linked_image_that_vanished_reports_404(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    original = make_image("a.jpg")
    _import(client, tmp_path / "source", copy_into_project=False)
    image_id = client.get("/api/v1/images").json()["data"]["images"][0]["id"]
    original.unlink()

    response = client.get(f"/api/v1/images/{image_id}/file")
    assert response.status_code == 404
    assert "missing" in response.json()["error"]["message"]


def test_detail_carries_neighbours_for_keyboard_navigation(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    for n in (1, 2, 3):
        make_image(f"img_{n}.jpg")
    _import(client, tmp_path / "source")
    listed = client.get("/api/v1/images").json()["data"]["images"]

    middle = client.get(f"/api/v1/images/{listed[1]['id']}").json()["data"]
    assert middle["previous_id"] == listed[0]["id"]
    assert middle["next_id"] == listed[2]["id"]


def test_class_crud(client: TestClient, opened: Project) -> None:
    created = _make_class(client, "Helmet")
    assert created["order_index"] == 0
    assert created["color"].startswith("#")

    renamed = client.patch(
        f"/api/v1/classes/{created['id']}", json={"name": "Safety Helmet"}
    )
    assert renamed.json()["data"]["name"] == "Safety Helmet"

    listed = client.get("/api/v1/classes").json()["data"]["classes"]
    assert [c["name"] for c in listed] == ["Safety Helmet"]


def test_duplicate_class_names_are_refused(client: TestClient, opened: Project) -> None:
    _make_class(client, "Helmet")
    response = client.post("/api/v1/classes", json={"name": "Helmet"})
    assert response.status_code == 422
    assert "already exists" in response.json()["error"]["message"]


def test_reorder_changes_export_order(client: TestClient, opened: Project) -> None:
    a = _make_class(client, "A")
    b = _make_class(client, "B")

    response = client.post(
        "/api/v1/classes/reorder", json={"ordered_ids": [b["id"], a["id"]]}
    )
    assert [c["name"] for c in response.json()["data"]["classes"]] == ["B", "A"]


def test_the_full_labeling_round_trip(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    _import(client, tmp_path / "source")
    image_id = client.get("/api/v1/images").json()["data"]["images"][0]["id"]
    helmet = _make_class(client, "Helmet")

    saved = client.put(
        f"/api/v1/annotations/{image_id}",
        json={
            "boxes": [
                {"class_id": helmet["id"], "cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3}
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert len(data["boxes"]) == 1
    assert data["image"]["status"] == "in_progress"

    reloaded = client.get(f"/api/v1/images/{image_id}").json()["data"]
    assert reloaded["boxes"][0]["cx"] == pytest.approx(0.5)


def test_saving_an_empty_set_marks_the_image_reviewed(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    _import(client, tmp_path / "source")
    image_id = client.get("/api/v1/images").json()["data"]["images"][0]["id"]

    response = client.put(
        f"/api/v1/annotations/{image_id}", json={"boxes": [], "status": "done"}
    )
    assert response.json()["data"]["image"]["status"] == "done"
    assert response.json()["data"]["boxes"] == []


def test_deleting_a_class_can_reassign_its_boxes(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    _import(client, tmp_path / "source")
    image_id = client.get("/api/v1/images").json()["data"]["images"][0]["id"]
    no_helmet = _make_class(client, "No_Helmet")
    ngob = _make_class(client, "Ngob")

    client.put(
        f"/api/v1/annotations/{image_id}",
        json={
            "boxes": [
                {"class_id": no_helmet["id"], "cx": 0.5, "cy": 0.5, "w": 0.2, "h": 0.2}
            ]
        },
    )

    usage = client.get(f"/api/v1/classes/{no_helmet['id']}/usage").json()["data"]
    assert (usage["annotations"], usage["images"]) == (1, 1)

    deleted = client.post(
        f"/api/v1/classes/{no_helmet['id']}/delete",
        json={"reassign_to": ngob["id"]},
    )
    assert deleted.status_code == 200, deleted.text
    assert [c["name"] for c in deleted.json()["data"]["classes"]] == ["Ngob"]

    boxes = client.get(f"/api/v1/annotations/{image_id}").json()["data"]
    assert boxes[0]["class_id"] == ngob["id"]


def test_deleting_a_class_can_discard_its_boxes(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    _import(client, tmp_path / "source")
    image_id = client.get("/api/v1/images").json()["data"]["images"][0]["id"]
    helmet = _make_class(client, "Helmet")
    client.put(
        f"/api/v1/annotations/{image_id}",
        json={
            "boxes": [
                {"class_id": helmet["id"], "cx": 0.5, "cy": 0.5, "w": 0.2, "h": 0.2}
            ]
        },
    )

    client.post(f"/api/v1/classes/{helmet['id']}/delete", json={})

    assert client.get(f"/api/v1/annotations/{image_id}").json()["data"] == []


def test_bulk_reassign_across_the_project(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    make_image("b.jpg")
    _import(client, tmp_path / "source")
    listed = client.get("/api/v1/images").json()["data"]["images"]
    helmet = _make_class(client, "Helmet")
    ngob = _make_class(client, "Ngob")

    for record in listed:
        client.put(
            f"/api/v1/annotations/{record['id']}",
            json={
                "boxes": [
                    {"class_id": helmet["id"], "cx": 0.5, "cy": 0.5, "w": 0.2, "h": 0.2}
                ]
            },
        )

    response = client.post(
        "/api/v1/annotations/reassign",
        json={"from_class": helmet["id"], "to_class": ngob["id"]},
    )
    assert response.json()["data"]["moved"] == 2


def test_status_filter_narrows_the_list(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    make_image("b.jpg")
    _import(client, tmp_path / "source")
    listed = client.get("/api/v1/images").json()["data"]["images"]
    client.patch(f"/api/v1/images/{listed[0]['id']}/status", json={"status": "done"})

    filtered = client.get("/api/v1/images", params={"status": "unlabeled"})
    assert [i["id"] for i in filtered.json()["data"]["images"]] == [listed[1]["id"]]


def test_an_invalid_status_is_rejected(
    client: TestClient, opened: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    _import(client, tmp_path / "source")
    image_id = client.get("/api/v1/images").json()["data"]["images"][0]["id"]

    response = client.patch(
        f"/api/v1/images/{image_id}/status", json={"status": "finished"}
    )
    assert response.status_code == 422
