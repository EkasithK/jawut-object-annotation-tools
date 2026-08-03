"""Recognising an existing YOLO dataset and turning it into a project."""

from __future__ import annotations

from pathlib import Path

import pytest

from jawut.db import connection
from jawut.services import annotations, classes, dataset, images
from tests.conftest import MakeImage


def write_labels(folder: Path, **files: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for stem, body in files.items():
        (folder / f"{stem}.txt").write_text(body, encoding="utf-8")


def write_yaml(path: Path, names: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    listed = ", ".join(f"'{name}'" for name in names)
    path.write_text(f"names: [{listed}]\n", encoding="utf-8")
    return path


# ── scanning ────────────────────────────────────────────────────────────────


def test_an_images_and_labels_pair_is_recognised(
    tmp_path: Path, make_image: MakeImage
) -> None:
    root = tmp_path / "helmet"
    make_image("a.jpg", folder=root / "images")
    make_image("b.jpg", folder=root / "images")
    write_labels(root / "labels", a="0 0.5 0.5 0.2 0.2\n")
    write_yaml(root / "data.yaml", ["helmet", "no_helmet"])

    found = dataset.scan(root)

    assert found.layout == "images_labels"
    assert found.image_count == 2
    assert found.label_count == 1
    assert found.class_names == ["helmet", "no_helmet"]
    assert found.data_yaml == root / "data.yaml"


def test_an_ultralytics_split_is_recognised(
    tmp_path: Path, make_image: MakeImage
) -> None:
    root = tmp_path / "helmet"
    for split in ("train", "valid", "test"):
        make_image(f"{split}.jpg", folder=root / split / "images")
        write_labels(root / split / "labels", **{split: "0 0.5 0.5 0.2 0.2\n"})
    write_yaml(root / "data.yaml", ["helmet"])

    found = dataset.scan(root)

    assert found.layout == "split"
    assert found.image_count == 3
    assert found.label_count == 3
    assert len(found.label_dirs) == 3


def test_a_flat_folder_of_images_and_labels_is_recognised(
    tmp_path: Path, make_image: MakeImage
) -> None:
    root = tmp_path / "flat"
    make_image("a.jpg", folder=root)
    write_labels(root, a="0 0.5 0.5 0.2 0.2\n")

    found = dataset.scan(root)

    assert found.layout == "flat"
    assert found.image_dirs == [root]
    assert found.label_dirs == [root]


def test_images_with_no_labels_are_reported_as_such(
    tmp_path: Path, make_image: MakeImage
) -> None:
    root = tmp_path / "raw"
    make_image("a.jpg", folder=root / "images")

    found = dataset.scan(root)

    assert found.layout == "images_only"
    assert found.image_count == 1
    assert found.label_count == 0
    assert "no labels yet" in found.summary


def test_an_empty_folder_says_so_rather_than_failing(tmp_path: Path) -> None:
    root = tmp_path / "nothing"
    root.mkdir()

    found = dataset.scan(root)

    assert found.layout == "empty"
    assert found.image_count == 0
    assert "No images found" in found.summary


def test_a_config_named_after_the_dataset_is_still_found(
    tmp_path: Path, make_image: MakeImage
) -> None:
    """Exports do not always call it data.yaml."""
    root = tmp_path / "helmet"
    make_image("a.jpg", folder=root / "images")
    write_yaml(root / "helmet_v3.yaml", ["helmet"])

    assert dataset.scan(root).class_names == ["helmet"]


def test_an_unreadable_config_does_not_stop_the_scan(
    tmp_path: Path, make_image: MakeImage
) -> None:
    root = tmp_path / "helmet"
    make_image("a.jpg", folder=root / "images")
    (root / "data.yaml").write_text("this: has no names\n", encoding="utf-8")

    found = dataset.scan(root)

    assert found.class_names == []
    assert found.data_yaml is None
    assert found.image_count == 1


def test_scanning_a_missing_folder_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(dataset.DatasetError, match="is not a folder"):
        dataset.scan(tmp_path / "nowhere")


def test_scanning_writes_nothing(tmp_path: Path, make_image: MakeImage) -> None:
    root = tmp_path / "helmet"
    make_image("a.jpg", folder=root / "images")
    before = sorted(p.name for p in root.rglob("*"))

    dataset.scan(root)

    assert sorted(p.name for p in root.rglob("*")) == before


# ── adopting ────────────────────────────────────────────────────────────────


def test_adopting_creates_a_project_with_named_classes(
    tmp_path: Path, make_image: MakeImage
) -> None:
    root = tmp_path / "helmet"
    make_image("a.jpg", folder=root / "images")
    make_image("b.jpg", folder=root / "images")
    write_labels(root / "labels", a="1 0.5 0.5 0.2 0.2\n")
    write_yaml(root / "data.yaml", ["no_helmet", "helmet"])

    result = dataset.adopt(tmp_path / "workspace", "Helmet", dataset.scan(root))

    assert result.images_imported == 2
    assert result.classes_created == 2
    assert result.boxes_created == 1
    assert result.images_labeled == 1

    conn = connection.connect(result.project.db_path)
    assert [c.name for c in classes.list_classes(conn)] == ["no_helmet", "helmet"]


def test_the_class_index_in_the_files_still_means_the_same_thing(
    tmp_path: Path, make_image: MakeImage
) -> None:
    """Index 1 in a .txt must land on the class the config declared at index 1."""
    root = tmp_path / "helmet"
    make_image("a.jpg", folder=root / "images")
    write_labels(root / "labels", a="1 0.5 0.5 0.2 0.2\n")
    write_yaml(root / "data.yaml", ["no_helmet", "helmet"])

    result = dataset.adopt(tmp_path / "workspace", "Helmet", dataset.scan(root))
    conn = connection.connect(result.project.db_path)

    image_id = images.list_images(conn)[0].id
    boxes = annotations.list_for_image(conn, image_id)
    by_id = {c.id: c.name for c in classes.list_classes(conn)}
    assert [by_id[b.class_id] for b in boxes] == ["helmet"]


def test_an_image_without_a_label_file_stays_unlabeled(
    tmp_path: Path, make_image: MakeImage
) -> None:
    """Missing means nobody looked; empty means someone looked and saw nothing."""
    root = tmp_path / "helmet"
    make_image("labeled.jpg", folder=root / "images")
    make_image("untouched.jpg", folder=root / "images")
    write_labels(root / "labels", labeled="0 0.5 0.5 0.2 0.2\n")
    write_yaml(root / "data.yaml", ["helmet"])

    result = dataset.adopt(tmp_path / "workspace", "Helmet", dataset.scan(root))
    conn = connection.connect(result.project.db_path)

    statuses = {img.filename: img.status for img in images.list_images(conn)}
    assert statuses["untouched.jpg"] == images.ImageStatus.UNLABELED
    assert statuses["labeled.jpg"] != images.ImageStatus.UNLABELED


def test_an_empty_label_file_marks_the_image_a_reviewed_background(
    tmp_path: Path, make_image: MakeImage
) -> None:
    root = tmp_path / "helmet"
    make_image("background.jpg", folder=root / "images")
    write_labels(root / "labels", background="")
    write_yaml(root / "data.yaml", ["helmet"])

    result = dataset.adopt(tmp_path / "workspace", "Helmet", dataset.scan(root))

    assert result.images_marked_empty == 1
    conn = connection.connect(result.project.db_path)
    statuses = {img.filename: img.status for img in images.list_images(conn)}
    assert statuses["background.jpg"] == images.ImageStatus.DONE


def test_classes_used_only_in_one_split_still_get_created(
    tmp_path: Path, make_image: MakeImage
) -> None:
    """Without a pass over every split first, test/'s class 2 would be dropped."""
    root = tmp_path / "helmet"
    make_image("t.jpg", folder=root / "train" / "images")
    make_image("v.jpg", folder=root / "test" / "images")
    write_labels(root / "train" / "labels", t="0 0.5 0.5 0.2 0.2\n")
    write_labels(root / "test" / "labels", v="2 0.5 0.5 0.2 0.2\n")

    result = dataset.adopt(tmp_path / "workspace", "Helmet", dataset.scan(root))

    assert result.classes_created == 3
    assert result.boxes_created == 2


def test_a_dataset_without_a_config_gets_placeholder_names(
    tmp_path: Path, make_image: MakeImage
) -> None:
    root = tmp_path / "helmet"
    make_image("a.jpg", folder=root / "images")
    write_labels(root / "labels", a="0 0.5 0.5 0.2 0.2\n1 0.4 0.4 0.1 0.1\n")

    result = dataset.adopt(tmp_path / "workspace", "Helmet", dataset.scan(root))
    conn = connection.connect(result.project.db_path)

    assert [c.name for c in classes.list_classes(conn)] == ["class_0", "class_1"]
    assert result.boxes_created == 2


def test_adopting_a_folder_with_no_images_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "nothing"
    root.mkdir()

    with pytest.raises(dataset.DatasetError, match="no images"):
        dataset.adopt(tmp_path / "workspace", "Empty", dataset.scan(root))
