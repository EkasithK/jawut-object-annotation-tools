from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from jawut.services import classes, exporter, images
from jawut.services.annotations import Box, replace_for_image
from jawut.services.projects import Project
from tests.conftest import MakeImage


@pytest.fixture
def stocked(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> dict[str, str]:
    """Four images, three classes, a mix of labeled / empty / untouched."""
    helmet = classes.create(conn, "Helmet")
    ngob = classes.create(conn, "Ngob")
    classes.create(conn, "No_Helmet")

    for name in ("a.jpg", "b.jpg", "c.jpg", "d.jpg"):
        make_image(name)
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    listed = images.list_images(conn)

    replace_for_image(
        conn,
        listed[0].id,
        [
            Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2),
            Box(class_id=ngob.id, cx=0.2, cy=0.2, w=0.1, h=0.1),
        ],
    )
    replace_for_image(
        conn, listed[1].id, [Box(class_id=helmet.id, cx=0.4, cy=0.4, w=0.3, h=0.3)]
    )
    # Reviewed and genuinely empty — a background image.
    replace_for_image(conn, listed[2].id, [], status=images.ImageStatus.DONE)
    # listed[3] stays untouched.

    return {"helmet": helmet.id, "ngob": ngob.id}


def _export(tmp_path: Path, project: Project, conn: sqlite3.Connection, **kwargs):
    options = exporter.ExportOptions(destination=tmp_path / "export", **kwargs)
    return exporter.export(conn, project.path, options)


def test_flat_export_writes_the_expected_tree(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)

    root = result.destination
    assert (root / "images").is_dir()
    assert (root / "labels").is_dir()
    assert (root / "data.yaml").is_file()
    assert (root / "export_manifest.json").is_file()
    assert not (root / "train").exists()


def test_split_export_writes_the_expected_tree(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn)

    for split in ("train", "val", "test"):
        assert (result.destination / split / "images").is_dir()
        assert (result.destination / split / "labels").is_dir()


def test_untouched_images_are_excluded_by_default(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)

    assert result.images_exported == 3
    assert len(list((result.destination / "images").iterdir())) == 3


def test_untouched_images_can_be_included(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(
        tmp_path,
        project,
        conn,
        layout=exporter.ExportLayout.FLAT,
        include_unlabeled=True,
    )
    assert result.images_exported == 4


def test_a_reviewed_empty_image_gets_an_empty_label_file(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    """The missing-vs-empty distinction, end to end: reviewed-and-empty must reach
    training as a real background image."""
    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)

    empty = result.destination / "labels" / "c.txt"
    assert empty.is_file()
    assert empty.read_text(encoding="utf-8") == ""
    assert result.empty_labels == 1


def test_every_exported_image_has_a_label_file(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)

    for image in (result.destination / "images").iterdir():
        assert (result.destination / "labels" / f"{image.stem}.txt").is_file()


def test_label_lines_are_valid_yolo(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)

    lines = (result.destination / "labels" / "a.txt").read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        fields = line.split()
        assert len(fields) == 5
        assert fields[0].isdigit()
        assert all(0.0 <= float(v) <= 1.0 for v in fields[1:])


def test_class_indices_follow_class_order(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)

    indices = {
        line.split()[0]
        for line in (result.destination / "labels" / "a.txt").read_text().splitlines()
    }
    # Helmet is order 0, Ngob is order 1.
    assert indices == {"0", "1"}
    assert result.class_names == ["Helmet", "Ngob", "No_Helmet"]


def test_reordering_classes_changes_the_exported_indices(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    live = classes.list_classes(conn)
    classes.reorder(conn, [live[1].id, live[0].id, live[2].id])

    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)

    assert result.class_names == ["Ngob", "Helmet", "No_Helmet"]
    # The Helmet box now carries index 1 rather than 0.
    lines = (result.destination / "labels" / "b.txt").read_text().split()
    assert lines[0] == "1"


def test_deleting_a_class_compacts_exported_indices(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    """No gap is ever left in the index space, whatever was deleted."""
    live = classes.list_classes(conn)
    classes.delete(conn, live[0].id, reassign_to=live[1].id)

    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)

    assert result.class_names == ["Ngob", "No_Helmet"]
    indices = set()
    for label in (result.destination / "labels").iterdir():
        for line in label.read_text().splitlines():
            indices.add(int(line.split()[0]))
    assert indices <= {0, 1}


def test_data_yaml_matches_the_ultralytics_shape(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn)
    document = yaml.safe_load(result.data_yaml.read_text(encoding="utf-8"))

    assert document["nc"] == 3
    assert document["names"] == ["Helmet", "Ngob", "No_Helmet"]
    assert document["train"] == "train/images"
    assert document["val"] == "val/images"
    assert document["test"] == "test/images"
    assert Path(document["path"]) == result.destination


def test_flat_data_yaml_points_train_and_val_at_the_same_folder(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn, layout=exporter.ExportLayout.FLAT)
    document = yaml.safe_load(result.data_yaml.read_text(encoding="utf-8"))

    assert document["train"] == "images"
    assert document["val"] == "images"
    assert "test" not in document


def test_the_manifest_records_everything_needed_to_reproduce(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    result = _export(tmp_path, project, conn, seed=7)
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))

    assert manifest["seed"] == 7
    assert manifest["layout"] == "split"
    assert manifest["ratios"]["train"] == pytest.approx(0.70)
    assert [c["name"] for c in manifest["classes"]] == [
        "Helmet",
        "Ngob",
        "No_Helmet",
    ]
    assert len(manifest["images"]) == result.images_exported
    assert {"filename", "split", "boxes", "status"} <= set(manifest["images"][0])


def test_the_same_seed_produces_the_same_split(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    first = exporter.export(
        conn,
        project.path,
        exporter.ExportOptions(destination=tmp_path / "one", seed=11),
    )
    second = exporter.export(
        conn,
        project.path,
        exporter.ExportOptions(destination=tmp_path / "two", seed=11),
    )

    def assignments(result: exporter.ExportResult) -> dict[str, str]:
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        return {i["filename"]: i["split"] for i in manifest["images"]}

    assert assignments(first) == assignments(second)


def test_a_different_seed_can_produce_a_different_split(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    helmet = classes.create(conn, "Helmet")
    for n in range(30):
        make_image(f"img_{n:02d}.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    for record in images.list_images(conn):
        replace_for_image(
            conn, record.id, [Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
        )

    def assignments(destination: Path, seed: int) -> dict[str, str]:
        result = exporter.export(
            conn,
            project.path,
            exporter.ExportOptions(destination=destination, seed=seed),
        )
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
        return {i["filename"]: i["split"] for i in manifest["images"]}

    assert assignments(tmp_path / "a", 1) != assignments(tmp_path / "b", 999)


def test_split_sizes_follow_the_ratios(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    helmet = classes.create(conn, "Helmet")
    for n in range(100):
        make_image(f"img_{n:03d}.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    for record in images.list_images(conn):
        replace_for_image(
            conn, record.id, [Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
        )

    result = _export(tmp_path, project, conn)

    assert result.counts_per_split["train"] == 70
    assert result.counts_per_split["val"] == 15
    assert result.counts_per_split["test"] == 15
    assert sum(result.counts_per_split.values()) == 100


def test_custom_ratios_are_honoured(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    helmet = classes.create(conn, "Helmet")
    for n in range(100):
        make_image(f"img_{n:03d}.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    for record in images.list_images(conn):
        replace_for_image(
            conn, record.id, [Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
        )

    result = _export(
        tmp_path,
        project,
        conn,
        ratios=exporter.SplitRatios(train=0.8, val=0.2, test=0.0),
    )

    assert result.counts_per_split["train"] == 80
    assert result.counts_per_split["val"] == 20
    assert result.counts_per_split["test"] == 0


def test_ratios_that_do_not_sum_to_one_are_rejected() -> None:
    with pytest.raises(ValueError, match="must sum to 1.0"):
        exporter.SplitRatios(train=0.8, val=0.3, test=0.2)


def test_a_rare_class_reaches_more_than_one_split(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    """Stratification exists for exactly this: without it a scarce class can land
    entirely in train, and validation numbers for it become meaningless."""
    common = classes.create(conn, "Helmet")
    rare = classes.create(conn, "Helmet_Ngob")

    for n in range(90):
        make_image(f"common_{n:03d}.jpg")
    for n in range(10):
        make_image(f"rare_{n:03d}.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")

    for record in images.list_images(conn):
        class_id = rare.id if record.filename.startswith("rare") else common.id
        replace_for_image(
            conn, record.id, [Box(class_id=class_id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
        )

    result = _export(tmp_path, project, conn)
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    rare_splits = {
        entry["split"]
        for entry in manifest["images"]
        if entry["filename"].startswith("rare")
    }

    assert len(rare_splits) > 1


def test_exporting_into_a_non_empty_folder_is_refused(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    destination = tmp_path / "export"
    destination.mkdir()
    (destination / "something.txt").write_text("in the way", encoding="utf-8")

    with pytest.raises(exporter.ExporterError, match="not empty"):
        _export(tmp_path, project, conn)


def test_exporting_without_classes_is_refused(
    conn: sqlite3.Connection, project: Project, tmp_path: Path
) -> None:
    with pytest.raises(exporter.ExporterError, match="no classes"):
        _export(tmp_path, project, conn)


def test_exporting_without_labeled_images_is_refused(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    classes.create(conn, "Helmet")
    make_image("a.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")

    with pytest.raises(exporter.ExporterError, match="no images to export"):
        _export(tmp_path, project, conn)


def test_a_missing_image_file_stops_the_export(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, stocked: dict[str, str]
) -> None:
    (project.images_dir / "a.jpg").unlink()

    with pytest.raises(exporter.ExporterError, match="missing"):
        _export(tmp_path, project, conn)
