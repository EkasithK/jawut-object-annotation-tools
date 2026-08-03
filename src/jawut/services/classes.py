"""Class management.

Classes are the part of this tool most likely to corrupt a dataset if done naively,
because in YOLO a class *is* its integer index. Everything here is built so that no
class operation ever needs to touch a label file:

* Classes have stable UUIDs. The contiguous YOLO index is derived from
  ``order_index`` at export time and stored nowhere.
* Deleting is a soft delete, and the annotations pointing at the class are either
  reassigned or removed first, in the same transaction.
* Reordering rewrites ``order_index`` only, which changes nothing until the next
  export.
"""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel

from jawut.util import new_id, now_iso

#: Distinct, colourblind-safe defaults handed out in order as classes are created.
#: Deliberately avoids the interface accent so a class never reads as "selected".
#: Chosen to survive the photograph, not to look calm next to each other.
#:
#: The previous palette included sand, olive, umber and a muted green — which are
#: the colours of dirt, vegetation and machinery, so on a real site photo those
#: classes became invisible. Every colour here is saturated past anything that
#: occurs naturally outdoors. The first four avoid the yellow-green of
#: high-visibility clothing and the yellow of heavy equipment as well, since a
#: project with four classes never reaches the last four.
DEFAULT_COLORS: tuple[str, ...] = (
    "#ff2d95",  # magenta
    "#00e5ff",  # cyan
    "#00ff9d",  # spring green
    "#a970ff",  # violet
    "#ff1744",  # red
    "#3d8bff",  # blue
    "#ff9100",  # orange
    "#ffe93d",  # yellow
)

_HEX_COLOR_LENGTH = 7


class ClassError(RuntimeError):
    """A class operation was rejected."""


class ObjectClass(BaseModel):
    id: str
    name: str
    color: str
    order_index: int


class ClassUsage(BaseModel):
    class_id: str
    name: str
    annotations: int
    images: int


def _row_to_class(row: sqlite3.Row) -> ObjectClass:
    return ObjectClass(
        id=str(row["id"]),
        name=str(row["name"]),
        color=str(row["color"]),
        order_index=int(row["order_index"]),
    )


def _validate_name(conn: sqlite3.Connection, name: str, exclude_id: str | None) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ClassError("class name cannot be empty")
    if len(cleaned) > 64:
        raise ClassError("class name cannot be longer than 64 characters")
    # YOLO's data.yaml is whitespace-delimited in practice and class names end up in
    # file paths during export, so keep them to a single token-friendly form.
    if any(ch in cleaned for ch in "\n\r\t"):
        raise ClassError("class name cannot contain line breaks or tabs")

    row = conn.execute(
        "SELECT id FROM classes WHERE name = ? AND deleted_at IS NULL",
        (cleaned,),
    ).fetchone()
    if row is not None and str(row["id"]) != exclude_id:
        raise ClassError(f"a class named '{cleaned}' already exists")
    return cleaned


def _validate_color(color: str) -> str:
    cleaned = color.strip().lower()
    if len(cleaned) != _HEX_COLOR_LENGTH or not cleaned.startswith("#"):
        raise ClassError("colour must be a hex value like #4c8dff")
    if any(ch not in "0123456789abcdef" for ch in cleaned[1:]):
        raise ClassError("colour must be a hex value like #4c8dff")
    return cleaned


def list_classes(conn: sqlite3.Connection) -> list[ObjectClass]:
    rows = conn.execute(
        "SELECT id, name, color, order_index FROM classes "
        "WHERE deleted_at IS NULL ORDER BY order_index, name"
    ).fetchall()
    return [_row_to_class(row) for row in rows]


def get(conn: sqlite3.Connection, class_id: str) -> ObjectClass:
    row = conn.execute(
        "SELECT id, name, color, order_index FROM classes "
        "WHERE id = ? AND deleted_at IS NULL",
        (class_id,),
    ).fetchone()
    if row is None:
        raise ClassError(f"no class with id {class_id}")
    return _row_to_class(row)


def create(
    conn: sqlite3.Connection, name: str, color: str | None = None
) -> ObjectClass:
    cleaned = _validate_name(conn, name, exclude_id=None)

    row = conn.execute(
        "SELECT COALESCE(MAX(order_index) + 1, 0) AS next FROM classes "
        "WHERE deleted_at IS NULL"
    ).fetchone()
    order_index = int(row["next"])

    chosen = (
        _validate_color(color)
        if color is not None
        else DEFAULT_COLORS[order_index % len(DEFAULT_COLORS)]
    )

    class_id = new_id()
    conn.execute(
        "INSERT INTO classes (id, name, color, order_index, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (class_id, cleaned, chosen, order_index, now_iso()),
    )
    conn.commit()
    return ObjectClass(id=class_id, name=cleaned, color=chosen, order_index=order_index)


def update(
    conn: sqlite3.Connection,
    class_id: str,
    name: str | None = None,
    color: str | None = None,
) -> ObjectClass:
    """Rename or recolour a class. Neither touches annotations."""
    existing = get(conn, class_id)

    new_name = existing.name if name is None else _validate_name(conn, name, class_id)
    new_color = existing.color if color is None else _validate_color(color)

    conn.execute(
        "UPDATE classes SET name = ?, color = ? WHERE id = ?",
        (new_name, new_color, class_id),
    )
    conn.commit()
    return ObjectClass(
        id=class_id,
        name=new_name,
        color=new_color,
        order_index=existing.order_index,
    )


def reorder(conn: sqlite3.Connection, ordered_ids: list[str]) -> list[ObjectClass]:
    """Set class order from a complete list of live class ids.

    The list must name every live class exactly once — a partial reorder would leave
    two classes sharing an ``order_index``, and the export index is derived from it.
    """
    live = {c.id for c in list_classes(conn)}
    given = set(ordered_ids)

    if len(ordered_ids) != len(given):
        raise ClassError("the same class appears more than once in the new order")
    if given != live:
        raise ClassError("the new order must list every class exactly once")

    try:
        for index, class_id in enumerate(ordered_ids):
            conn.execute(
                "UPDATE classes SET order_index = ? WHERE id = ?", (index, class_id)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return list_classes(conn)


def usage(conn: sqlite3.Connection, class_id: str) -> ClassUsage:
    """Count what a delete would affect, for the confirmation dialog."""
    cls = get(conn, class_id)
    row = conn.execute(
        "SELECT COUNT(*) AS boxes, COUNT(DISTINCT image_id) AS images "
        "FROM annotations WHERE class_id = ?",
        (class_id,),
    ).fetchone()
    return ClassUsage(
        class_id=class_id,
        name=cls.name,
        annotations=int(row["boxes"]),
        images=int(row["images"]),
    )


def delete(
    conn: sqlite3.Connection, class_id: str, reassign_to: str | None = None
) -> ClassUsage:
    """Delete a class, either moving its annotations elsewhere or removing them.

    ``reassign_to`` names the class the existing boxes move to; ``None`` deletes
    them. Both paths run in one transaction with the soft delete, so a failure
    leaves the class and its boxes exactly as they were.
    """
    before = usage(conn, class_id)

    if reassign_to is not None:
        if reassign_to == class_id:
            raise ClassError("cannot reassign a class to itself")
        get(conn, reassign_to)  # raises if it does not exist or is deleted

    try:
        if reassign_to is None:
            conn.execute("DELETE FROM annotations WHERE class_id = ?", (class_id,))
        else:
            conn.execute(
                "UPDATE annotations SET class_id = ?, updated_at = ? "
                "WHERE class_id = ?",
                (reassign_to, now_iso(), class_id),
            )

        conn.execute(
            "UPDATE classes SET deleted_at = ? WHERE id = ?", (now_iso(), class_id)
        )
        # Close the gap so the remaining classes stay 0..n-1 and export indices do
        # not depend on how many classes were deleted along the way.
        _compact_order(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return before


def _compact_order(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id FROM classes WHERE deleted_at IS NULL ORDER BY order_index, name"
    ).fetchall()
    for index, row in enumerate(rows):
        conn.execute(
            "UPDATE classes SET order_index = ? WHERE id = ?", (index, row["id"])
        )


def export_index_map(conn: sqlite3.Connection) -> dict[str, int]:
    """Map class id to the YOLO integer it gets in an export.

    This is the only place a class ever acquires an integer, and it is computed
    fresh each time rather than stored.
    """
    return {cls.id: index for index, cls in enumerate(list_classes(conn))}
