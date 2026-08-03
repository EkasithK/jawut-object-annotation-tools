"""Bounding box storage.

All coordinates are normalized center form (``cx cy w h``) in ``[0,1]``, matching
YOLO exactly so import and export are lossless. Pixel coordinates exist only inside
the canvas view transform.

Saving is whole-image: the client sends the complete set of boxes for one image and
this module replaces them. That keeps the client free to batch edits without an
id-reconciliation protocol, and makes every save a single atomic transaction.
"""

from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel, Field

from jawut.services.images import ImageStatus
from jawut.util import new_id, now_iso

#: Boxes below this fraction of the image in either dimension are almost always
#: an accidental click rather than a real annotation.
MIN_SIDE = 0.001


class AnnotationError(RuntimeError):
    """An annotation operation was rejected."""


class Box(BaseModel):
    """One bounding box. ``id`` is absent for a box the client has just drawn."""

    id: str | None = None
    class_id: str
    cx: float = Field(ge=0.0, le=1.0)
    cy: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)


class StoredBox(Box):
    id: str


def _clamp_to_image(box: Box) -> Box:
    """Pull a box fully inside the image, preserving as much of it as possible.

    Dragging past the edge is constant during labeling, so the correct behaviour is
    to trim the box rather than reject the edit.
    """
    left = max(0.0, box.cx - box.w / 2)
    top = max(0.0, box.cy - box.h / 2)
    right = min(1.0, box.cx + box.w / 2)
    bottom = min(1.0, box.cy + box.h / 2)

    width = right - left
    height = bottom - top
    if width < MIN_SIDE or height < MIN_SIDE:
        raise AnnotationError("box is too small or entirely outside the image")

    return Box(
        id=box.id,
        class_id=box.class_id,
        cx=left + width / 2,
        cy=top + height / 2,
        w=width,
        h=height,
    )


def _known_class_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT id FROM classes WHERE deleted_at IS NULL").fetchall()
    return {str(row["id"]) for row in rows}


def list_for_image(conn: sqlite3.Connection, image_id: str) -> list[StoredBox]:
    rows = conn.execute(
        "SELECT id, class_id, cx, cy, w, h FROM annotations "
        "WHERE image_id = ? ORDER BY created_at, id",
        (image_id,),
    ).fetchall()
    return [
        StoredBox(
            id=str(row["id"]),
            class_id=str(row["class_id"]),
            cx=float(row["cx"]),
            cy=float(row["cy"]),
            w=float(row["w"]),
            h=float(row["h"]),
        )
        for row in rows
    ]


def replace_for_image(
    conn: sqlite3.Connection,
    image_id: str,
    boxes: list[Box],
    status: ImageStatus | None = None,
) -> list[StoredBox]:
    """Replace every box on an image, optionally setting its status.

    An empty list is meaningful and is stored as such: it marks an image the user
    reviewed and found to contain nothing, which exports as an empty ``.txt``. That
    is only distinguishable from an untouched image because ``status`` moves off
    ``unlabeled``.
    """
    image = conn.execute(
        "SELECT id, status FROM images WHERE id = ?", (image_id,)
    ).fetchone()
    if image is None:
        raise AnnotationError(f"no image with id {image_id}")

    known = _known_class_ids(conn)
    unknown = {box.class_id for box in boxes} - known
    if unknown:
        raise AnnotationError(f"unknown class id: {sorted(unknown)[0]}")

    cleaned = [_clamp_to_image(box) for box in boxes]

    previous = list_for_image(conn, image_id)
    timestamp = now_iso()

    if status is not None:
        new_status = status
    elif str(image["status"]) == ImageStatus.UNLABELED.value:
        # First edit of an untouched image, including one saved with no boxes:
        # it has now been looked at, and must never read as untouched again.
        new_status = ImageStatus.IN_PROGRESS
    else:
        new_status = ImageStatus(str(image["status"]))

    try:
        conn.execute("DELETE FROM annotations WHERE image_id = ?", (image_id,))
        for box in cleaned:
            conn.execute(
                "INSERT INTO annotations (id, image_id, class_id, cx, cy, w, h, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    box.id or new_id(),
                    image_id,
                    box.class_id,
                    box.cx,
                    box.cy,
                    box.w,
                    box.h,
                    timestamp,
                    timestamp,
                ),
            )

        conn.execute(
            "UPDATE images SET status = ?, updated_at = ? WHERE id = ?",
            (new_status.value, timestamp, image_id),
        )
        _record(
            conn,
            image_id,
            "replace_boxes",
            {
                "before": [b.model_dump() for b in previous],
                "after": [b.model_dump() for b in cleaned],
            },
            timestamp,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return list_for_image(conn, image_id)


def reassign_class(conn: sqlite3.Connection, from_class: str, to_class: str) -> int:
    """Move every box of one class to another. Returns how many moved."""
    known = _known_class_ids(conn)
    for class_id in (from_class, to_class):
        if class_id not in known:
            raise AnnotationError(f"unknown class id: {class_id}")
    if from_class == to_class:
        return 0

    timestamp = now_iso()
    try:
        cursor = conn.execute(
            "UPDATE annotations SET class_id = ?, updated_at = ? WHERE class_id = ?",
            (to_class, timestamp, from_class),
        )
        moved = cursor.rowcount
        _record(
            conn,
            None,
            "reassign_class",
            {"from": from_class, "to": to_class, "count": moved},
            timestamp,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return moved


def _record(
    conn: sqlite3.Connection,
    image_id: str | None,
    action: str,
    payload: dict[str, object],
    timestamp: str,
) -> None:
    conn.execute(
        "INSERT INTO edit_log (image_id, action, payload, created_at) "
        "VALUES (?, ?, ?, ?)",
        (image_id, action, json.dumps(payload), timestamp),
    )


def history(
    conn: sqlite3.Connection, image_id: str, limit: int = 50
) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT id, action, payload, created_at FROM edit_log "
        "WHERE image_id = ? ORDER BY id DESC LIMIT ?",
        (image_id, limit),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "action": str(row["action"]),
            "payload": json.loads(str(row["payload"])),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]
