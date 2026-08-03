from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from jawut.services import images
from jawut.services.projects import Project
from tests.conftest import MakeImage


def test_scan_finds_images_and_ignores_other_files(
    tmp_path: Path, make_image: MakeImage
) -> None:
    source = tmp_path / "source"
    make_image("a.jpg")
    make_image("b.png")
    (source / "notes.txt").write_text("not an image", encoding="utf-8")

    assert [p.name for p in images.scan_folder(source)] == ["a.jpg", "b.png"]


def test_scan_orders_numerically_not_lexicographically(
    tmp_path: Path, make_image: MakeImage
) -> None:
    for n in (1, 2, 9, 10, 100):
        make_image(f"frame_{n}.jpg")

    found = [p.name for p in images.scan_folder(tmp_path / "source")]
    assert found == [
        "frame_1.jpg",
        "frame_2.jpg",
        "frame_9.jpg",
        "frame_10.jpg",
        "frame_100.jpg",
    ]


def test_scan_can_stay_shallow(tmp_path: Path, make_image: MakeImage) -> None:
    source = tmp_path / "source"
    make_image("top.jpg")
    make_image("nested.jpg", folder=source / "sub")

    assert len(images.scan_folder(source, recursive=False)) == 1
    assert len(images.scan_folder(source, recursive=True)) == 2


def test_scan_rejects_a_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(images.ImageError, match="not a folder"):
        images.scan_folder(tmp_path / "nope")


def test_import_copies_files_into_the_project(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    make_image("b.jpg")

    result = images.import_folder(conn, project.images_dir, tmp_path / "source")

    assert result.imported == 2
    assert sorted(p.name for p in project.images_dir.iterdir()) == ["a.jpg", "b.jpg"]


def test_import_records_real_dimensions(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("wide.jpg", size=(800, 200))
    images.import_folder(conn, project.images_dir, tmp_path / "source")

    record = images.list_images(conn)[0]
    assert (record.width, record.height) == (800, 200)


def test_imported_images_start_unlabeled(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")

    assert images.list_images(conn)[0].status is images.ImageStatus.UNLABELED


def test_import_can_link_instead_of_copying(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    original = make_image("a.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source", copy=False)

    record = images.list_images(conn)[0]
    assert list(project.images_dir.iterdir()) == []
    assert images.resolve_path(conn, record.id, project.path) == original.resolve()


def test_a_managed_image_resolves_inside_the_project(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")

    record = images.list_images(conn)[0]
    resolved = images.resolve_path(conn, record.id, project.path)
    assert resolved == project.images_dir / "a.jpg"
    assert resolved.is_file()


def test_identical_files_are_deduplicated(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    original = make_image("a.jpg")
    shutil.copy2(original, tmp_path / "source" / "copy_of_a.jpg")

    result = images.import_folder(conn, project.images_dir, tmp_path / "source")

    assert (result.imported, result.duplicates) == (1, 1)
    assert len(images.list_images(conn)) == 1


def test_reimporting_the_same_folder_adds_nothing(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    second = images.import_folder(conn, project.images_dir, tmp_path / "source")

    assert (second.imported, second.duplicates) == (0, 1)


def test_different_images_sharing_a_name_both_import(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    source = tmp_path / "source"
    make_image("frame.jpg", folder=source / "cam1", color=(10, 20, 30))
    make_image("frame.jpg", folder=source / "cam2", color=(200, 100, 50))

    result = images.import_folder(conn, project.images_dir, source)

    assert result.imported == 2
    assert sorted(p.name for p in project.images_dir.iterdir()) == [
        "frame.jpg",
        "frame_2.jpg",
    ]


def test_an_unreadable_file_is_skipped_with_a_reason(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("good.jpg")
    (tmp_path / "source" / "broken.jpg").write_bytes(b"not really a jpeg")

    result = images.import_folder(conn, project.images_dir, tmp_path / "source")

    assert result.imported == 1
    assert len(result.skipped) == 1
    assert "broken.jpg" in result.skipped[0].path
    assert "unreadable" in result.skipped[0].reason


def test_one_bad_file_does_not_abort_the_run(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    (tmp_path / "source" / "b.jpg").write_bytes(b"garbage")
    make_image("c.jpg")

    result = images.import_folder(conn, project.images_dir, tmp_path / "source")

    assert result.imported == 2
    assert result.examined == 3


def test_list_filters_by_status(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    make_image("b.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    first = images.list_images(conn)[0]
    images.set_status(conn, first.id, images.ImageStatus.DONE)

    done = images.list_images(conn, status=images.ImageStatus.DONE)
    unlabeled = images.list_images(conn, status=images.ImageStatus.UNLABELED)

    assert [i.id for i in done] == [first.id]
    assert len(unlabeled) == 1


def test_list_paginates(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    for n in range(5):
        make_image(f"img_{n}.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")

    page = images.list_images(conn, limit=2, offset=2)
    assert [i.filename for i in page] == ["img_2.jpg", "img_3.jpg"]


def test_counts_tally_every_status(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    for n in range(3):
        make_image(f"img_{n}.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    listed = images.list_images(conn)
    images.set_status(conn, listed[0].id, images.ImageStatus.DONE)
    images.set_status(conn, listed[1].id, images.ImageStatus.NEEDS_REVIEW)

    tally = images.counts(conn)
    assert (tally.total, tally.done, tally.needs_review, tally.unlabeled) == (
        3,
        1,
        1,
        1,
    )


def test_neighbours_walk_the_natural_order(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    for n in (1, 2, 10):
        make_image(f"frame_{n}.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    listed = images.list_images(conn)

    assert [i.filename for i in listed] == [
        "frame_1.jpg",
        "frame_2.jpg",
        "frame_10.jpg",
    ]
    assert images.neighbours(conn, listed[1].id) == (listed[0].id, listed[2].id)


def test_neighbours_are_none_at_the_ends(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    make_image("a.jpg")
    make_image("b.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    listed = images.list_images(conn)

    assert images.neighbours(conn, listed[0].id)[0] is None
    assert images.neighbours(conn, listed[-1].id)[1] is None


def test_neighbours_respect_the_active_filter(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> None:
    for n in range(4):
        make_image(f"img_{n}.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    listed = images.list_images(conn)
    # Mark the two in the middle done, leaving 0 and 3 unlabeled.
    images.set_status(conn, listed[1].id, images.ImageStatus.DONE)
    images.set_status(conn, listed[2].id, images.ImageStatus.DONE)

    _, following = images.neighbours(
        conn, listed[0].id, status=images.ImageStatus.UNLABELED
    )
    assert following == listed[3].id


def test_unknown_ids_are_rejected(conn: sqlite3.Connection) -> None:
    for call in (
        lambda: images.get(conn, "nope"),
        lambda: images.neighbours(conn, "nope"),
        lambda: images.set_status(conn, "nope", images.ImageStatus.DONE),
    ):
        with pytest.raises(images.ImageError, match="no image with id"):
            call()


def test_resolve_path_rejects_an_unknown_id(
    conn: sqlite3.Connection, project: Project
) -> None:
    with pytest.raises(images.ImageError, match="no image with id"):
        images.resolve_path(conn, "nope", project.path)
