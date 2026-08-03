from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from tests.conftest import MakeImage

from jawut.services import annotations as ann
from jawut.services import classes, images
from jawut.services.projects import Project


@pytest.fixture
def helmet(conn: sqlite3.Connection) -> classes.ObjectClass:
    return classes.create(conn, "Helmet")


@pytest.fixture
def ngob(conn: sqlite3.Connection) -> classes.ObjectClass:
    return classes.create(conn, "Ngob")


@pytest.fixture
def image_id(
    conn: sqlite3.Connection, project: Project, tmp_path: Path, make_image: MakeImage
) -> str:
    make_image("a.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    return images.list_images(conn)[0].id


def test_saving_boxes_stores_them(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    saved = ann.replace_for_image(
        conn,
        image_id,
        [
            ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.3),
            ann.Box(class_id=helmet.id, cx=0.1, cy=0.1, w=0.05, h=0.05),
        ],
    )
    assert len(saved) == 2
    assert all(box.id for box in saved)


def test_saving_replaces_rather_than_appends(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )
    second = ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.1, cy=0.1, w=0.1, h=0.1)]
    )

    assert len(second) == 1
    assert second[0].cx == pytest.approx(0.1)


def test_a_first_save_moves_the_image_off_unlabeled(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )
    assert images.get(conn, image_id).status is images.ImageStatus.IN_PROGRESS


def test_saving_no_boxes_still_marks_the_image_as_looked_at(
    conn: sqlite3.Connection, image_id: str
) -> None:
    """An empty save is a real answer: reviewed, nothing here. It must not read as
    untouched, because export treats the two differently."""
    ann.replace_for_image(conn, image_id, [])

    record = images.get(conn, image_id)
    assert record.status is not images.ImageStatus.UNLABELED
    assert record.annotation_count == 0


def test_an_explicit_status_wins(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    ann.replace_for_image(
        conn,
        image_id,
        [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)],
        status=images.ImageStatus.DONE,
    )
    assert images.get(conn, image_id).status is images.ImageStatus.DONE


def test_saving_does_not_downgrade_a_finished_image(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    images.set_status(conn, image_id, images.ImageStatus.DONE)
    ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )
    assert images.get(conn, image_id).status is images.ImageStatus.DONE


def test_a_box_hanging_over_the_edge_is_trimmed(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    saved = ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.05, cy=0.5, w=0.2, h=0.2)]
    )
    box = saved[0]

    assert box.cx - box.w / 2 == pytest.approx(0.0)
    assert box.cx + box.w / 2 == pytest.approx(0.15)
    assert box.w == pytest.approx(0.15)


def test_a_box_touching_the_far_edge_is_trimmed(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    saved = ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.98, cy=0.5, w=0.2, h=0.2)]
    )
    assert saved[0].cx + saved[0].w / 2 == pytest.approx(1.0)


def test_a_full_frame_box_survives_untouched(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    saved = ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=1.0, h=1.0)]
    )
    assert (saved[0].w, saved[0].h) == (1.0, 1.0)


def test_a_degenerate_box_is_rejected(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    with pytest.raises(ann.AnnotationError, match="too small"):
        ann.replace_for_image(
            conn,
            image_id,
            [ann.Box(class_id=helmet.id, cx=0.0, cy=0.5, w=0.0005, h=0.2)],
        )


def test_an_unknown_class_is_rejected(conn: sqlite3.Connection, image_id: str) -> None:
    with pytest.raises(ann.AnnotationError, match="unknown class id"):
        ann.replace_for_image(
            conn, image_id, [ann.Box(class_id="nope", cx=0.5, cy=0.5, w=0.2, h=0.2)]
        )


def test_a_deleted_class_is_rejected(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    classes.delete(conn, helmet.id)
    with pytest.raises(ann.AnnotationError, match="unknown class id"):
        ann.replace_for_image(
            conn,
            image_id,
            [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)],
        )


def test_an_unknown_image_is_rejected(
    conn: sqlite3.Connection, helmet: classes.ObjectClass
) -> None:
    with pytest.raises(ann.AnnotationError, match="no image with id"):
        ann.replace_for_image(
            conn, "nope", [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
        )


def test_a_rejected_save_leaves_the_previous_boxes_intact(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )

    with pytest.raises(ann.AnnotationError):
        ann.replace_for_image(
            conn,
            image_id,
            [
                ann.Box(class_id=helmet.id, cx=0.4, cy=0.4, w=0.2, h=0.2),
                ann.Box(class_id="nope", cx=0.5, cy=0.5, w=0.2, h=0.2),
            ],
        )

    surviving = ann.list_for_image(conn, image_id)
    assert len(surviving) == 1
    assert surviving[0].cx == pytest.approx(0.5)


def test_changing_a_box_class_keeps_its_geometry(
    conn: sqlite3.Connection,
    image_id: str,
    helmet: classes.ObjectClass,
    ngob: classes.ObjectClass,
) -> None:
    saved = ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )
    moved = ann.replace_for_image(
        conn,
        image_id,
        [
            ann.Box(
                id=saved[0].id,
                class_id=ngob.id,
                cx=saved[0].cx,
                cy=saved[0].cy,
                w=saved[0].w,
                h=saved[0].h,
            )
        ],
    )

    assert moved[0].id == saved[0].id
    assert moved[0].class_id == ngob.id
    assert moved[0].cx == pytest.approx(0.5)


def test_reassign_moves_every_box_of_a_class(
    conn: sqlite3.Connection,
    project: Project,
    tmp_path: Path,
    make_image: MakeImage,
    helmet: classes.ObjectClass,
    ngob: classes.ObjectClass,
) -> None:
    make_image("a.jpg")
    make_image("b.jpg")
    images.import_folder(conn, project.images_dir, tmp_path / "source")
    listed = images.list_images(conn)
    for record in listed:
        ann.replace_for_image(
            conn,
            record.id,
            [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)],
        )

    assert ann.reassign_class(conn, helmet.id, ngob.id) == 2
    for record in listed:
        assert ann.list_for_image(conn, record.id)[0].class_id == ngob.id


def test_reassigning_a_class_to_itself_changes_nothing(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )
    assert ann.reassign_class(conn, helmet.id, helmet.id) == 0


def test_reassign_rejects_an_unknown_class(
    conn: sqlite3.Connection, helmet: classes.ObjectClass
) -> None:
    with pytest.raises(ann.AnnotationError, match="unknown class id"):
        ann.reassign_class(conn, helmet.id, "nope")


def test_deleting_an_image_removes_its_boxes(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )
    conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 0


def test_history_records_each_save(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )
    ann.replace_for_image(conn, image_id, [])

    entries = ann.history(conn, image_id)
    assert [e["action"] for e in entries] == ["replace_boxes", "replace_boxes"]
    # Newest first, and the last save cleared the boxes.
    assert entries[0]["payload"]["after"] == []
    assert len(entries[1]["payload"]["after"]) == 1


def test_history_captures_what_was_there_before(
    conn: sqlite3.Connection, image_id: str, helmet: classes.ObjectClass
) -> None:
    ann.replace_for_image(
        conn, image_id, [ann.Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )
    ann.replace_for_image(conn, image_id, [])

    latest = ann.history(conn, image_id)[0]
    assert len(latest["payload"]["before"]) == 1
