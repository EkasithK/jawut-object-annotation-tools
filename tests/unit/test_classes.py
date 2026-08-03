from __future__ import annotations

import sqlite3

import pytest

from jawut.services import classes
from jawut.services.annotations import Box, replace_for_image
from jawut.services.images import ImageStatus
from jawut.util import new_id, now_iso


def _add_image(conn: sqlite3.Connection, name: str = "a.jpg") -> str:
    image_id = new_id()
    stamp = now_iso()
    conn.execute(
        "INSERT INTO images (id, filename, stored_path, is_managed, width, height, "
        "sha256, status, sort_key, created_at, updated_at) "
        "VALUES (?, ?, ?, 1, 640, 480, ?, ?, ?, ?, ?)",
        (
            image_id,
            name,
            name,
            new_id(),
            ImageStatus.UNLABELED.value,
            name,
            stamp,
            stamp,
        ),
    )
    conn.commit()
    return image_id


def test_create_assigns_sequential_order(conn: sqlite3.Connection) -> None:
    first = classes.create(conn, "Helmet")
    second = classes.create(conn, "Ngob")
    assert (first.order_index, second.order_index) == (0, 1)


def test_create_hands_out_distinct_default_colours(conn: sqlite3.Connection) -> None:
    made = [classes.create(conn, f"c{i}") for i in range(4)]
    assert len({c.color for c in made}) == 4


def test_create_accepts_an_explicit_colour(conn: sqlite3.Connection) -> None:
    assert classes.create(conn, "Helmet", "#ABCDEF").color == "#abcdef"


@pytest.mark.parametrize("color", ["red", "#abc", "#12345g", "4c8dff", ""])
def test_create_rejects_a_bad_colour(conn: sqlite3.Connection, color: str) -> None:
    with pytest.raises(classes.ClassError, match="hex"):
        classes.create(conn, "Helmet", color)


def test_create_rejects_a_duplicate_name(conn: sqlite3.Connection) -> None:
    classes.create(conn, "Helmet")
    with pytest.raises(classes.ClassError, match="already exists"):
        classes.create(conn, "Helmet")


@pytest.mark.parametrize("name", ["", "   ", "x" * 65, "has\nbreak", "has\ttab"])
def test_create_rejects_a_bad_name(conn: sqlite3.Connection, name: str) -> None:
    with pytest.raises(classes.ClassError):
        classes.create(conn, name)


def test_names_are_trimmed(conn: sqlite3.Connection) -> None:
    assert classes.create(conn, "  Helmet  ").name == "Helmet"


def test_rename_keeps_order_and_colour(conn: sqlite3.Connection) -> None:
    created = classes.create(conn, "Helmet")
    renamed = classes.update(conn, created.id, name="Safety Helmet")

    assert renamed.name == "Safety Helmet"
    assert renamed.order_index == created.order_index
    assert renamed.color == created.color


def test_renaming_a_class_to_its_own_name_is_allowed(conn: sqlite3.Connection) -> None:
    created = classes.create(conn, "Helmet")
    assert classes.update(conn, created.id, name="Helmet").name == "Helmet"


def test_rename_rejects_another_live_name(conn: sqlite3.Connection) -> None:
    classes.create(conn, "Helmet")
    other = classes.create(conn, "Ngob")

    with pytest.raises(classes.ClassError, match="already exists"):
        classes.update(conn, other.id, name="Helmet")


def test_recolour_keeps_the_name(conn: sqlite3.Connection) -> None:
    created = classes.create(conn, "Helmet")
    assert classes.update(conn, created.id, color="#111111").name == "Helmet"


def test_reorder_rewrites_indices(conn: sqlite3.Connection) -> None:
    a = classes.create(conn, "A")
    b = classes.create(conn, "B")
    c = classes.create(conn, "C")

    reordered = classes.reorder(conn, [c.id, a.id, b.id])
    assert [cls.name for cls in reordered] == ["C", "A", "B"]
    assert [cls.order_index for cls in reordered] == [0, 1, 2]


def test_reorder_rejects_a_partial_list(conn: sqlite3.Connection) -> None:
    a = classes.create(conn, "A")
    classes.create(conn, "B")

    with pytest.raises(classes.ClassError, match="every class exactly once"):
        classes.reorder(conn, [a.id])


def test_reorder_rejects_duplicates(conn: sqlite3.Connection) -> None:
    a = classes.create(conn, "A")
    classes.create(conn, "B")

    with pytest.raises(classes.ClassError, match="more than once"):
        classes.reorder(conn, [a.id, a.id])


def test_usage_counts_boxes_and_images(conn: sqlite3.Connection) -> None:
    helmet = classes.create(conn, "Helmet")
    one, two = _add_image(conn, "a.jpg"), _add_image(conn, "b.jpg")

    replace_for_image(
        conn,
        one,
        [
            Box(class_id=helmet.id, cx=0.3, cy=0.3, w=0.1, h=0.1),
            Box(class_id=helmet.id, cx=0.6, cy=0.6, w=0.1, h=0.1),
        ],
    )
    replace_for_image(
        conn, two, [Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )

    counted = classes.usage(conn, helmet.id)
    assert (counted.annotations, counted.images) == (3, 2)


def test_delete_with_reassignment_moves_every_box(conn: sqlite3.Connection) -> None:
    no_helmet = classes.create(conn, "No_Helmet")
    ngob = classes.create(conn, "Ngob")
    image = _add_image(conn)
    replace_for_image(
        conn, image, [Box(class_id=no_helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )

    removed = classes.delete(conn, no_helmet.id, reassign_to=ngob.id)

    assert removed.annotations == 1
    assert [c.name for c in classes.list_classes(conn)] == ["Ngob"]
    remaining = conn.execute("SELECT class_id FROM annotations").fetchall()
    assert [str(r["class_id"]) for r in remaining] == [ngob.id]


def test_delete_without_reassignment_removes_the_boxes(
    conn: sqlite3.Connection,
) -> None:
    helmet = classes.create(conn, "Helmet")
    image = _add_image(conn)
    replace_for_image(
        conn, image, [Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )

    classes.delete(conn, helmet.id)

    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 0
    assert classes.list_classes(conn) == []


def test_delete_compacts_the_remaining_order(conn: sqlite3.Connection) -> None:
    a = classes.create(conn, "A")
    classes.create(conn, "B")
    classes.create(conn, "C")

    classes.delete(conn, a.id)

    assert [c.order_index for c in classes.list_classes(conn)] == [0, 1]


def test_a_deleted_name_can_be_reused(conn: sqlite3.Connection) -> None:
    first = classes.create(conn, "Ngob")
    classes.delete(conn, first.id)

    revived = classes.create(conn, "Ngob")
    assert revived.id != first.id


def test_delete_rejects_reassigning_to_itself(conn: sqlite3.Connection) -> None:
    helmet = classes.create(conn, "Helmet")
    with pytest.raises(classes.ClassError, match="itself"):
        classes.delete(conn, helmet.id, reassign_to=helmet.id)


def test_delete_rejects_an_unknown_target(conn: sqlite3.Connection) -> None:
    helmet = classes.create(conn, "Helmet")
    with pytest.raises(classes.ClassError, match="no class with id"):
        classes.delete(conn, helmet.id, reassign_to="does-not-exist")


def test_a_failed_delete_leaves_everything_untouched(
    conn: sqlite3.Connection,
) -> None:
    helmet = classes.create(conn, "Helmet")
    image = _add_image(conn)
    replace_for_image(
        conn, image, [Box(class_id=helmet.id, cx=0.5, cy=0.5, w=0.2, h=0.2)]
    )

    with pytest.raises(classes.ClassError):
        classes.delete(conn, helmet.id, reassign_to="does-not-exist")

    assert [c.name for c in classes.list_classes(conn)] == ["Helmet"]
    assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 1


def test_get_refuses_a_deleted_class(conn: sqlite3.Connection) -> None:
    helmet = classes.create(conn, "Helmet")
    classes.delete(conn, helmet.id)

    with pytest.raises(classes.ClassError, match="no class with id"):
        classes.get(conn, helmet.id)


def test_export_index_map_follows_order_not_creation(
    conn: sqlite3.Connection,
) -> None:
    a = classes.create(conn, "A")
    b = classes.create(conn, "B")
    classes.reorder(conn, [b.id, a.id])

    assert classes.export_index_map(conn) == {b.id: 0, a.id: 1}


def test_export_index_map_skips_deleted_classes(conn: sqlite3.Connection) -> None:
    a = classes.create(conn, "A")
    b = classes.create(conn, "B")
    c = classes.create(conn, "C")
    classes.delete(conn, b.id)

    assert classes.export_index_map(conn) == {a.id: 0, c.id: 1}
