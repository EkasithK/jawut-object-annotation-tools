from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jawut.services import classes, images, importer
from jawut.services.projects import Project
from tests.conftest import MakeImage


@pytest.fixture
def labels_dir(tmp_path: Path) -> Path:
    target = tmp_path / "labels"
    target.mkdir()
    return target


@pytest.fixture
def imported(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> list[str]:
    """Three images in the project, named a/b/c so labels can match by stem."""
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        make_image(name, size=(1000, 500))
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    return [record.filename for record in images.list_images(conn)]


# ─── Line parsing ────────────────────────────────────────────────────────────


def _parse_one(tmp_path: Path, line: str, width: int = 1000, height: int = 500):
    path = tmp_path / "one.txt"
    path.write_text(line, encoding="utf-8")
    return importer.parse_label_file(path, width, height)


def test_a_normal_detection_line_parses(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "1 0.5 0.4 0.2 0.3\n")
    assert result.issues == []
    assert len(result.boxes) == 1
    box = result.boxes[0]
    assert box.source_class == 1
    assert (box.cx, box.cy, box.w, box.h) == pytest.approx((0.5, 0.4, 0.2, 0.3))


def test_several_lines_parse(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "0 0.5 0.5 0.1 0.1\n1 0.2 0.2 0.1 0.1\n")
    assert len(result.boxes) == 2


def test_blank_lines_are_ignored(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "\n0 0.5 0.5 0.1 0.1\n\n\n")
    assert len(result.boxes) == 1
    assert result.issues == []


def test_a_pose_line_keeps_the_box_and_drops_keypoints(tmp_path: Path) -> None:
    """The thesis labeler wrote 5 box fields plus 3 per keypoint. Those files must
    be ingestible without hand-editing."""
    keypoints = " ".join(["0.4 0.4 2"] * 5)
    result = _parse_one(tmp_path, f"0 0.5 0.5 0.2 0.2 {keypoints}\n")

    assert len(result.boxes) == 1
    assert result.boxes[0].w == pytest.approx(0.2)
    assert [i.kind for i in result.issues] == [importer.IssueKind.KEYPOINTS_DROPPED]
    assert result.issues[0].is_repair


def test_pixel_coordinates_are_normalized(tmp_path: Path) -> None:
    # 500 500 200 100 on a 1000x500 image is the centre, a fifth wide.
    result = _parse_one(tmp_path, "0 500 250 200 100\n")

    box = result.boxes[0]
    assert (box.cx, box.cy, box.w, box.h) == pytest.approx((0.5, 0.5, 0.2, 0.2))
    assert [i.kind for i in result.issues] == [importer.IssueKind.PIXELS_NORMALIZED]


def test_marginal_overflow_is_clamped_silently_enough(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "0 0.5 0.5 1.0001 0.2\n")

    assert len(result.boxes) == 1
    assert result.boxes[0].w == pytest.approx(1.0)
    assert [i.kind for i in result.issues] == [importer.IssueKind.COORDS_CLAMPED]


def test_a_wildly_out_of_range_value_is_quarantined(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "0 0.5 0.5 1.4 0.2\n")

    assert result.boxes == []
    assert [i.kind for i in result.issues] == [importer.IssueKind.OUT_OF_RANGE]


@pytest.mark.parametrize(
    "line",
    ["0 0.5 0.5", "0", "", "0 0.5 0.5 0.2", "not a label at all"],
)
def test_short_lines_are_malformed(tmp_path: Path, line: str) -> None:
    result = _parse_one(tmp_path, f"{line}\n")
    assert result.boxes == []
    if line:
        assert result.issues[0].kind is importer.IssueKind.MALFORMED


def test_non_numeric_values_are_malformed(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "0 a b c d\n")
    assert result.boxes == []
    assert result.issues[0].kind is importer.IssueKind.MALFORMED


def test_a_negative_class_index_is_rejected(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "-1 0.5 0.5 0.2 0.2\n")
    assert result.boxes == []
    assert result.issues[0].kind is importer.IssueKind.UNKNOWN_CLASS


@pytest.mark.parametrize("line", ["0 0.5 0.5 0 0.2", "0 0.5 0.5 0.2 -0.3"])
def test_a_non_positive_side_is_degenerate(tmp_path: Path, line: str) -> None:
    result = _parse_one(tmp_path, f"{line}\n")
    assert result.boxes == []
    assert result.issues[0].kind is importer.IssueKind.DEGENERATE


def test_a_box_entirely_outside_the_image_is_degenerate(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "0 1.0 0.5 0.0005 0.2\n")
    assert result.boxes == []
    assert result.issues[-1].kind is importer.IssueKind.DEGENERATE


def test_a_box_overhanging_the_edge_is_trimmed(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "0 0.05 0.5 0.3 0.2\n")

    box = result.boxes[0]
    assert box.cx - box.w / 2 == pytest.approx(0.0)
    assert box.w == pytest.approx(0.2)


def test_issue_line_numbers_point_at_the_right_line(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "0 0.5 0.5 0.1 0.1\nbroken\n0 0.2 0.2 0.1 0.1\n")
    assert [i.line for i in result.issues] == [2]


def test_an_empty_file_is_recorded_as_empty_not_missing(tmp_path: Path) -> None:
    result = _parse_one(tmp_path, "")
    assert result.was_empty is True
    assert result.boxes == []
    assert result.issues == []


# ─── data.yaml ───────────────────────────────────────────────────────────────


def test_class_names_read_from_a_list(tmp_path: Path) -> None:
    path = tmp_path / "data.yaml"
    path.write_text("nc: 2\nnames: ['No_Helmet', 'Safety-Helmet']\n", encoding="utf-8")
    assert importer.read_class_names(path) == ["No_Helmet", "Safety-Helmet"]


def test_class_names_read_from_a_mapping(tmp_path: Path) -> None:
    path = tmp_path / "data.yaml"
    path.write_text("names:\n  1: Ngob\n  0: Helmet\n", encoding="utf-8")
    assert importer.read_class_names(path) == ["Helmet", "Ngob"]


def test_a_data_yaml_without_names_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "data.yaml"
    path.write_text("train: images\n", encoding="utf-8")
    with pytest.raises(importer.ImporterError, match="no 'names'"):
        importer.read_class_names(path)


def test_data_yaml_is_found_beside_the_labels(labels_dir: Path) -> None:
    (labels_dir / "data.yaml").write_text("names: [a]\n", encoding="utf-8")
    assert importer.find_data_yaml(labels_dir) == labels_dir / "data.yaml"


def test_data_yaml_is_found_one_level_up(labels_dir: Path) -> None:
    """Exported datasets put data.yaml at the root with labels/ beneath it."""
    parent_yaml = labels_dir.parent / "data.yaml"
    parent_yaml.write_text("names: [a]\n", encoding="utf-8")
    assert importer.find_data_yaml(labels_dir) == parent_yaml


# ─── Preview ─────────────────────────────────────────────────────────────────


def test_preview_reports_matches_and_misses(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (labels_dir / "zzz.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    result = importer.preview(conn, labels_dir)

    assert result.label_files == 2
    assert result.matched_images == 1
    assert result.unmatched_labels == ["zzz.txt"]
    assert result.images_without_labels == 2


def test_preview_uses_data_yaml_names(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    (labels_dir / "data.yaml").write_text(
        "names: ['No_Helmet', 'Safety-Helmet']\n", encoding="utf-8"
    )
    (labels_dir / "a.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    result = importer.preview(conn, labels_dir)

    assert result.source_classes.from_data_yaml is True
    assert result.source_classes.names == ["No_Helmet", "Safety-Helmet"]


def test_preview_reads_an_explicitly_named_data_yaml(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path, tmp_path: Path
) -> None:
    """The dataset's yaml is often nowhere near the labels folder."""
    elsewhere = tmp_path / "somewhere_else" / "data.yaml"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text("names: ['No_Helmet', 'Safety-Helmet']\n", encoding="utf-8")
    (labels_dir / "a.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    result = importer.preview(conn, labels_dir, elsewhere)

    assert result.source_classes.from_data_yaml is True
    assert result.source_classes.names == ["No_Helmet", "Safety-Helmet"]
    assert result.source_classes.data_yaml_path == str(elsewhere)


def test_an_explicit_data_yaml_wins_over_the_one_beside_the_labels(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path, tmp_path: Path
) -> None:
    (labels_dir / "data.yaml").write_text("names: ['wrong']\n", encoding="utf-8")
    chosen = tmp_path / "chosen.yaml"
    chosen.write_text("names: ['right']\n", encoding="utf-8")
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    result = importer.preview(conn, labels_dir, chosen)

    assert result.source_classes.names == ["right"]


def test_preview_rejects_a_data_yaml_that_is_not_there(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path, tmp_path: Path
) -> None:
    with pytest.raises(importer.ImporterError, match="is not a file"):
        importer.preview(conn, labels_dir, tmp_path / "nothing.yaml")


def test_preview_invents_names_without_a_data_yaml(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    (labels_dir / "a.txt").write_text("2 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    result = importer.preview(conn, labels_dir)

    assert result.source_classes.from_data_yaml is False
    assert result.source_classes.names == ["class_0", "class_1", "class_2"]


def test_preview_extends_names_past_what_data_yaml_declares(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    """A class present in the files but missing from data.yaml still needs a row
    in the mapping table, or its boxes would vanish unexplained."""
    (labels_dir / "data.yaml").write_text("names: ['only_one']\n", encoding="utf-8")
    (labels_dir / "a.txt").write_text("3 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    result = importer.preview(conn, labels_dir)

    assert len(result.source_classes.names) == 4
    assert result.source_classes.names[0] == "only_one"


def test_preview_counts_boxes_per_source_class(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    (labels_dir / "a.txt").write_text(
        "0 0.5 0.5 0.2 0.2\n0 0.2 0.2 0.1 0.1\n1 0.8 0.8 0.1 0.1\n", encoding="utf-8"
    )

    assert importer.preview(conn, labels_dir).box_counts == {0: 2, 1: 1}


def test_preview_writes_nothing(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    importer.preview(conn, labels_dir)

    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 0
    assert all(
        record.status is images.ImageStatus.UNLABELED
        for record in images.list_images(conn)
    )


def test_preview_rejects_a_missing_folder(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    with pytest.raises(importer.ImporterError, match="not a folder"):
        importer.preview(conn, tmp_path / "nowhere")


# ─── Apply ───────────────────────────────────────────────────────────────────


def test_apply_creates_boxes_under_the_mapped_class(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    result = importer.apply(conn, labels_dir, {0: helmet.id})

    assert (result.images_labeled, result.boxes_created) == (1, 1)
    stored = conn.execute("SELECT class_id FROM annotations").fetchone()
    assert str(stored["class_id"]) == helmet.id


def test_apply_honours_an_ignored_class(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text(
        "0 0.5 0.5 0.2 0.2\n1 0.2 0.2 0.1 0.1\n", encoding="utf-8"
    )

    result = importer.apply(conn, labels_dir, {0: helmet.id, 1: None})

    assert result.boxes_created == 1
    assert result.skipped_boxes == 1


def test_a_class_missing_from_the_mapping_is_ignored(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text(
        "0 0.5 0.5 0.2 0.2\n7 0.2 0.2 0.1 0.1\n", encoding="utf-8"
    )

    result = importer.apply(conn, labels_dir, {0: helmet.id})

    assert result.boxes_created == 1
    assert result.skipped_boxes == 1


def test_two_source_classes_can_merge_into_one(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    ngob = classes.create(conn, "Ngob")
    (labels_dir / "a.txt").write_text(
        "0 0.5 0.5 0.2 0.2\n1 0.2 0.2 0.1 0.1\n", encoding="utf-8"
    )

    result = importer.apply(conn, labels_dir, {0: ngob.id, 1: ngob.id})

    assert result.boxes_created == 2


def test_a_labeled_image_becomes_in_progress(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    importer.apply(conn, labels_dir, {0: helmet.id})

    a = next(r for r in images.list_images(conn) if r.filename == "a.jpg")
    assert a.status is images.ImageStatus.IN_PROGRESS


def test_an_empty_label_file_marks_the_image_done_not_unlabeled(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    """This is the missing-vs-empty distinction, and it decides what export writes."""
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text("", encoding="utf-8")

    result = importer.apply(conn, labels_dir, {0: helmet.id})

    a = next(r for r in images.list_images(conn) if r.filename == "a.jpg")
    assert a.status is images.ImageStatus.DONE
    assert a.annotation_count == 0
    assert result.images_marked_empty == 1


def test_an_image_with_no_label_file_stays_unlabeled(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    importer.apply(conn, labels_dir, {0: helmet.id})

    b = next(r for r in images.list_images(conn) if r.filename == "b.jpg")
    assert b.status is images.ImageStatus.UNLABELED


def test_a_file_whose_boxes_were_all_rejected_needs_review(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text("garbage line here\n", encoding="utf-8")

    importer.apply(conn, labels_dir, {0: helmet.id})

    a = next(r for r in images.list_images(conn) if r.filename == "a.jpg")
    assert a.status is images.ImageStatus.NEEDS_REVIEW


def test_apply_overwrites_existing_boxes_by_default(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text(
        "0 0.5 0.5 0.2 0.2\n0 0.1 0.1 0.1 0.1\n", encoding="utf-8"
    )
    importer.apply(conn, labels_dir, {0: helmet.id})

    (labels_dir / "a.txt").write_text("0 0.9 0.9 0.05 0.05\n", encoding="utf-8")
    importer.apply(conn, labels_dir, {0: helmet.id})

    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 1


def test_apply_can_leave_already_labeled_images_alone(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    importer.apply(conn, labels_dir, {0: helmet.id})

    (labels_dir / "a.txt").write_text(
        "0 0.1 0.1 0.1 0.1\n0 0.2 0.2 0.1 0.1\n", encoding="utf-8"
    )
    result = importer.apply(conn, labels_dir, {0: helmet.id}, overwrite=False)

    assert result.boxes_created == 0
    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 1


def test_apply_rejects_an_unknown_target_class(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    with pytest.raises(importer.ImporterError, match="unknown class id"):
        importer.apply(conn, labels_dir, {0: "does-not-exist"})


def test_a_rejected_mapping_writes_nothing(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    with pytest.raises(importer.ImporterError):
        importer.apply(conn, labels_dir, {0: "does-not-exist"})

    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 0
    assert all(
        r.status is images.ImageStatus.UNLABELED for r in images.list_images(conn)
    )


def test_unmatched_label_files_are_left_alone(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    helmet = classes.create(conn, "Helmet")
    (labels_dir / "unknown_image.txt").write_text(
        "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
    )

    result = importer.apply(conn, labels_dir, {0: helmet.id})

    assert result.images_labeled == 0
    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 0


def test_the_two_class_helmet_dataset_maps_onto_four_classes(
    conn: sqlite3.Connection, imported: list[str], labels_dir: Path
) -> None:
    """The real migration: an existing 2-class export lands in the 4-class taxonomy,
    with the old Safety-Helmet boxes becoming Helmet and No_Helmet kept as-is."""
    helmet = classes.create(conn, "Helmet")
    classes.create(conn, "Helmet_Ngob")
    classes.create(conn, "Ngob")
    no_helmet = classes.create(conn, "No_Helmet")

    (labels_dir / "data.yaml").write_text(
        "nc: 2\nnames: ['No_Helmet', 'Safety-Helmet']\n", encoding="utf-8"
    )
    (labels_dir / "a.txt").write_text(
        "0 0.3 0.3 0.1 0.1\n1 0.7 0.7 0.1 0.1\n", encoding="utf-8"
    )
    (labels_dir / "b.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    preview = importer.preview(conn, labels_dir)
    assert preview.source_classes.names == ["No_Helmet", "Safety-Helmet"]
    assert preview.box_counts == {0: 1, 1: 2}

    result = importer.apply(conn, labels_dir, {0: no_helmet.id, 1: helmet.id})

    assert (result.images_labeled, result.boxes_created) == (2, 3)
    by_class = dict(
        conn.execute(
            "SELECT class_id, COUNT(*) FROM annotations GROUP BY class_id"
        ).fetchall()
    )
    assert by_class[helmet.id] == 2
    assert by_class[no_helmet.id] == 1
