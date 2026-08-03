"""The real migration, end to end.

Reproduces the job this tool exists for: an existing 2-class helmet dataset
(``No_Helmet``, ``Safety-Helmet``) relabeled to the 4-class taxonomy in
``docs/ANNOTATION_GUIDELINE.md`` — ``Helmet``, ``Helmet_Ngob``, ``Ngob``,
``No_Helmet`` — and exported for training.

The fixture deliberately includes everything that makes a real label folder
awkward: pose-format lines left over from the previous labeler, pixel
coordinates, a box hanging off the frame, an empty file that means "reviewed, no
objects", a label with no matching image, and an image with no label.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from jawut import session
from jawut.services.projects import Project
from tests.conftest import MakeImage

IMAGE_COUNT = 24
SOURCE_CLASSES = ["No_Helmet", "Safety-Helmet"]
TARGET_CLASSES = ["Helmet", "Helmet_Ngob", "Ngob", "No_Helmet"]


@pytest.fixture
def legacy_dataset(tmp_path: Path, make_image: MakeImage) -> Path:
    """A 2-class YOLO export shaped like the existing helmet dataset."""
    root = tmp_path / "legacy"
    images_dir = root / "images"
    labels_dir = root / "labels"
    labels_dir.mkdir(parents=True)

    for index in range(IMAGE_COUNT):
        make_image(f"frame_{index}.jpg", folder=images_dir, size=(1280, 720))

    # data.yaml at the dataset root, with labels/ beneath — the layout every
    # Roboflow and Ultralytics export uses.
    (root / "data.yaml").write_text(
        yaml.safe_dump(
            {
                "train": "images",
                "val": "images",
                "nc": 2,
                "names": SOURCE_CLASSES,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    for index in range(IMAGE_COUNT):
        name = f"frame_{index}.txt"

        if index == 0:
            # Reviewed and genuinely empty: a background image.
            (labels_dir / name).write_text("", encoding="utf-8")
        elif index == 1:
            # Pose format from the previous labeler: 5 box fields + 3 per keypoint.
            keypoints = " ".join(["0.5 0.5 2"] * 5)
            (labels_dir / name).write_text(
                f"1 0.5 0.5 0.2 0.3 {keypoints}\n", encoding="utf-8"
            )
        elif index == 2:
            # Pixel coordinates on a 1280x720 image.
            (labels_dir / name).write_text("0 640 360 256 216\n", encoding="utf-8")
        elif index == 3:
            # A box hanging off the left edge.
            (labels_dir / name).write_text("1 0.05 0.5 0.3 0.2\n", encoding="utf-8")
        elif index == 4:
            (labels_dir / name).write_text("this line is broken\n", encoding="utf-8")
        elif index == 5:
            # No label file at all: nobody has looked at this image.
            continue
        else:
            source_class = index % 2
            (labels_dir / name).write_text(
                f"{source_class} 0.5 0.45 0.18 0.24\n"
                f"{1 - source_class} 0.2 0.2 0.1 0.12\n",
                encoding="utf-8",
            )

    # A label whose image is not in this dataset.
    (labels_dir / "frame_from_another_shoot.txt").write_text(
        "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
    )

    return root


@pytest.fixture
def opened(client: TestClient, tmp_path: Path) -> Project:
    response = client.post(
        "/api/v1/projects",
        json={"name": "Helmet Relabel", "parent_dir": str(tmp_path / "workspace")},
    )
    assert response.status_code == 201, response.text
    return session.require_project()


def test_the_full_two_to_four_class_migration(
    client: TestClient, opened: Project, legacy_dataset: Path, tmp_path: Path
) -> None:
    headers: dict[str, str] = {}

    # ── 1. Bring in the images ────────────────────────────────────────────────
    imported = client.post(
        "/api/v1/images/import",
        json={"source": str(legacy_dataset / "images")},
        headers=headers,
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["data"]["imported"] == IMAGE_COUNT

    # ── 2. Create the 4-class taxonomy ────────────────────────────────────────
    class_ids: dict[str, str] = {}
    for name in TARGET_CLASSES:
        created = client.post("/api/v1/classes", json={"name": name})
        assert created.status_code == 201, created.text
        class_ids[name] = created.json()["data"]["id"]

    # ── 3. Preview the legacy labels ──────────────────────────────────────────
    preview = client.post(
        "/api/v1/labels/preview", json={"labels_dir": str(legacy_dataset / "labels")}
    ).json()["data"]

    # data.yaml sits one level above labels/, and must still be found.
    assert preview["source_classes"]["from_data_yaml"] is True
    assert preview["source_classes"]["names"] == SOURCE_CLASSES
    assert preview["unmatched_labels"] == ["frame_from_another_shoot.txt"]
    assert preview["images_without_labels"] == 1

    kinds = {issue["kind"] for issue in preview["issues"]}
    assert "keypoints_dropped" in kinds
    assert "pixels_normalized" in kinds
    assert "malformed" in kinds
    assert "unmatched_label" in kinds

    # ── 4. Import, mapping the old classes onto the new taxonomy ──────────────
    result = client.post(
        "/api/v1/labels/import",
        json={
            "labels_dir": str(legacy_dataset / "labels"),
            "class_mapping": {
                "0": class_ids["No_Helmet"],
                "1": class_ids["Helmet"],
            },
            "overwrite": True,
        },
    )
    assert result.status_code == 200, result.text
    imported_labels = result.json()["data"]

    assert imported_labels["boxes_created"] > 0
    # The empty file must land as reviewed-and-empty, not as untouched.
    assert imported_labels["images_marked_empty"] == 1

    counts = client.get("/api/v1/images").json()["data"]["counts"]
    # frame_5 has no label file and must still read as untouched.
    assert counts["unlabeled"] == 1
    # frame_4's only line was malformed, so it needs a human.
    assert counts["needs_review"] == 1
    assert counts["done"] == 1

    # ── 5. Reclassify: some Helmet boxes are really Helmet_Ngob ───────────────
    listed = client.get("/api/v1/images").json()["data"]["images"]
    reclassified = 0
    for record in listed:
        detail = client.get(f"/api/v1/images/{record['id']}").json()["data"]
        boxes = detail["boxes"]
        if not boxes or reclassified >= 4:
            continue
        changed = [
            {**box, "class_id": class_ids["Helmet_Ngob"]}
            if box["class_id"] == class_ids["Helmet"]
            else box
            for box in boxes
        ]
        if changed != boxes:
            saved = client.put(
                f"/api/v1/annotations/{record['id']}",
                json={"boxes": changed, "status": "done"},
            )
            assert saved.status_code == 200, saved.text
            reclassified += 1

    assert reclassified > 0

    # ── 6. Retire No_Helmet by folding it into Ngob ───────────────────────────
    usage = client.get(f"/api/v1/classes/{class_ids['No_Helmet']}/usage").json()["data"]
    assert usage["annotations"] > 0

    deleted = client.post(
        f"/api/v1/classes/{class_ids['No_Helmet']}/delete",
        json={"reassign_to": class_ids["Ngob"]},
    )
    assert deleted.status_code == 200, deleted.text
    remaining = [c["name"] for c in deleted.json()["data"]["classes"]]
    assert remaining == ["Helmet", "Helmet_Ngob", "Ngob"]

    # No annotation may still point at the retired class.
    for record in client.get("/api/v1/images").json()["data"]["images"]:
        for box in client.get(f"/api/v1/annotations/{record['id']}").json()["data"]:
            assert box["class_id"] != class_ids["No_Helmet"]

    # ── 7. Export a split dataset ─────────────────────────────────────────────
    destination = tmp_path / "export"
    exported = client.post(
        "/api/v1/export",
        json={
            "destination": str(destination),
            "layout": "split",
            "ratios": {"train": 0.7, "val": 0.15, "test": 0.15},
            "seed": 42,
            "include_unlabeled": False,
        },
    )
    assert exported.status_code == 200, exported.text
    report = exported.json()["data"]

    assert report["class_names"] == ["Helmet", "Helmet_Ngob", "Ngob"]
    # The one untouched image must not have been exported.
    assert report["images_exported"] == IMAGE_COUNT - 1
    # The reviewed-empty image exports as a background.
    assert report["empty_labels"] >= 1

    # ── 8. Verify what actually landed on disk ────────────────────────────────
    document = yaml.safe_load((destination / "data.yaml").read_text(encoding="utf-8"))
    assert document["nc"] == 3
    assert document["names"] == ["Helmet", "Helmet_Ngob", "Ngob"]
    assert document["train"] == "train/images"

    total_images = 0
    for split in ("train", "val", "test"):
        image_files = sorted((destination / split / "images").iterdir())
        total_images += len(image_files)
        for image in image_files:
            label = destination / split / "labels" / f"{image.stem}.txt"
            assert label.is_file(), f"{image.name} has no label file"
            for line in label.read_text(encoding="utf-8").splitlines():
                fields = line.split()
                assert len(fields) == 5
                assert 0 <= int(fields[0]) < 3
                assert all(0.0 <= float(v) <= 1.0 for v in fields[1:])

    assert total_images == report["images_exported"]

    manifest = json.loads((destination / "export_manifest.json").read_text())
    assert manifest["seed"] == 42
    assert len(manifest["images"]) == report["images_exported"]

    # frame_5 was never opened and must appear nowhere in the export.
    assert all(entry["filename"] != "frame_5.jpg" for entry in manifest["images"])


def test_the_migration_is_reproducible(
    client: TestClient, opened: Project, legacy_dataset: Path, tmp_path: Path
) -> None:
    """Two exports of the same project with the same seed are identical."""
    client.post(
        "/api/v1/images/import", json={"source": str(legacy_dataset / "images")}
    )
    helmet = client.post("/api/v1/classes", json={"name": "Helmet"}).json()["data"]
    no_helmet = client.post("/api/v1/classes", json={"name": "No_Helmet"}).json()[
        "data"
    ]
    client.post(
        "/api/v1/labels/import",
        json={
            "labels_dir": str(legacy_dataset / "labels"),
            "class_mapping": {"0": no_helmet["id"], "1": helmet["id"]},
        },
    )

    def export_to(name: str) -> dict[str, str]:
        response = client.post(
            "/api/v1/export",
            json={"destination": str(tmp_path / name), "layout": "split", "seed": 7},
        )
        assert response.status_code == 200, response.text
        manifest = json.loads(
            (tmp_path / name / "export_manifest.json").read_text(encoding="utf-8")
        )
        return {entry["filename"]: entry["split"] for entry in manifest["images"]}

    assert export_to("first") == export_to("second")
