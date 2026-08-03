"""Image import and listing.

Images are either **managed** — copied into ``<project>/images/`` so the project
folder is self-contained and can be moved or backed up by copying it — or **linked**,
left where they are and referenced by absolute path. Copying is the default because
it is the behaviour that survives a non-technical user reorganising their photos;
linking exists for datasets too large to duplicate.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from jawut.util import natural_sort_key, new_id, now_iso

IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
)

_HASH_CHUNK = 1 << 20


class ImageStatus(StrEnum):
    UNLABELED = "unlabeled"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"


class ImageError(RuntimeError):
    """An image operation was rejected."""


class ImageRecord(BaseModel):
    id: str
    filename: str
    width: int
    height: int
    status: ImageStatus
    annotation_count: int = 0


class SkippedImage(BaseModel):
    path: str
    reason: str


class ImportResult(BaseModel):
    imported: int
    duplicates: int
    skipped: list[SkippedImage]

    @property
    def examined(self) -> int:
        return self.imported + self.duplicates + len(self.skipped)


class StatusCounts(BaseModel):
    unlabeled: int = 0
    in_progress: int = 0
    done: int = 0
    needs_review: int = 0
    total: int = 0


def scan_folder(folder: Path, recursive: bool = True) -> list[Path]:
    """Return image files under ``folder``, in natural order."""
    if not folder.is_dir():
        raise ImageError(f"'{folder}' is not a folder")

    walker: Iterator[Path] = folder.rglob("*") if recursive else folder.glob("*")
    found = [
        path
        for path in walker
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    found.sort(key=lambda p: natural_sort_key(str(p.relative_to(folder))))
    return found


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_destination(images_dir: Path, filename: str) -> Path:
    """Pick a free name in the project image folder.

    Two source folders can easily both contain ``frame_0001.jpg``; the files are
    already known to differ, since identical ones are caught by hash first.
    """
    candidate = images_dir / filename
    if not candidate.exists():
        return candidate

    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 2
    while True:
        candidate = images_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def import_folder(
    conn: sqlite3.Connection,
    images_dir: Path,
    source: Path,
    recursive: bool = True,
    copy: bool = True,
) -> ImportResult:
    """Import every image under ``source`` into the project.

    Files that are not readable images are skipped with a reason rather than
    aborting the run — one corrupt file in a folder of 1,340 must not cost the user
    the whole import.
    """
    candidates = scan_folder(source, recursive=recursive)

    imported = 0
    duplicates = 0
    skipped: list[SkippedImage] = []

    for path in candidates:
        try:
            with Image.open(path) as handle:
                handle.verify()
            # verify() consumes the file object, so reopen to read dimensions.
            with Image.open(path) as handle:
                width, height = handle.size
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            skipped.append(SkippedImage(path=str(path), reason=f"unreadable: {exc}"))
            continue

        if width <= 0 or height <= 0:
            skipped.append(SkippedImage(path=str(path), reason="zero-sized image"))
            continue

        digest = hash_file(path)
        existing = conn.execute(
            "SELECT id FROM images WHERE sha256 = ?", (digest,)
        ).fetchone()
        if existing is not None:
            duplicates += 1
            continue

        if copy:
            images_dir.mkdir(parents=True, exist_ok=True)
            destination = _unique_destination(images_dir, path.name)
            try:
                shutil.copy2(path, destination)
            except OSError as exc:
                skipped.append(
                    SkippedImage(path=str(path), reason=f"could not copy: {exc}")
                )
                continue
            stored_path = destination.name
            filename = destination.name
        else:
            stored_path = str(path.resolve())
            filename = path.name

        timestamp = now_iso()
        conn.execute(
            "INSERT INTO images (id, filename, stored_path, is_managed, width, "
            "height, sha256, status, sort_key, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id(),
                filename,
                stored_path,
                1 if copy else 0,
                width,
                height,
                digest,
                ImageStatus.UNLABELED.value,
                natural_sort_key(filename),
                timestamp,
                timestamp,
            ),
        )
        imported += 1

    conn.commit()
    return ImportResult(imported=imported, duplicates=duplicates, skipped=skipped)


def resolve_path(conn: sqlite3.Connection, image_id: str, project_dir: Path) -> Path:
    """Return the on-disk location of an image, managed or linked."""
    row = conn.execute(
        "SELECT stored_path, is_managed FROM images WHERE id = ?", (image_id,)
    ).fetchone()
    if row is None:
        raise ImageError(f"no image with id {image_id}")

    stored = str(row["stored_path"])
    if int(row["is_managed"]):
        return project_dir / "images" / stored
    return Path(stored)


def _row_to_record(row: sqlite3.Row) -> ImageRecord:
    return ImageRecord(
        id=str(row["id"]),
        filename=str(row["filename"]),
        width=int(row["width"]),
        height=int(row["height"]),
        status=ImageStatus(str(row["status"])),
        annotation_count=int(row["annotation_count"]),
    )


_LIST_SELECT = (
    "SELECT i.id, i.filename, i.width, i.height, i.status, "
    "COUNT(a.id) AS annotation_count "
    "FROM images i LEFT JOIN annotations a ON a.image_id = i.id "
)

_LIST_QUERY = (
    f"{_LIST_SELECT}"
    "WHERE (? IS NULL OR i.status = ?) "
    "GROUP BY i.id ORDER BY i.sort_key, i.filename "
    "LIMIT ? OFFSET ?"
)

_GET_QUERY = f"{_LIST_SELECT}WHERE i.id = ? GROUP BY i.id"


def list_images(
    conn: sqlite3.Connection,
    status: ImageStatus | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[ImageRecord]:
    wanted = None if status is None else status.value
    # SQLite reads a negative LIMIT as unbounded, which keeps this one statement.
    rows = conn.execute(
        _LIST_QUERY, (wanted, wanted, -1 if limit is None else limit, offset)
    ).fetchall()
    return [_row_to_record(row) for row in rows]


def get(conn: sqlite3.Connection, image_id: str) -> ImageRecord:
    row = conn.execute(_GET_QUERY, (image_id,)).fetchone()
    if row is None:
        raise ImageError(f"no image with id {image_id}")
    return _row_to_record(row)


def set_status(
    conn: sqlite3.Connection, image_id: str, status: ImageStatus
) -> ImageRecord:
    cursor = conn.execute(
        "UPDATE images SET status = ?, updated_at = ? WHERE id = ?",
        (status.value, now_iso(), image_id),
    )
    if cursor.rowcount == 0:
        raise ImageError(f"no image with id {image_id}")
    conn.commit()
    return get(conn, image_id)


def counts(conn: sqlite3.Connection) -> StatusCounts:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM images GROUP BY status"
    ).fetchall()
    tally = {str(row["status"]): int(row["n"]) for row in rows}
    return StatusCounts(
        unlabeled=tally.get(ImageStatus.UNLABELED.value, 0),
        in_progress=tally.get(ImageStatus.IN_PROGRESS.value, 0),
        done=tally.get(ImageStatus.DONE.value, 0),
        needs_review=tally.get(ImageStatus.NEEDS_REVIEW.value, 0),
        total=sum(tally.values()),
    )


def neighbours(
    conn: sqlite3.Connection, image_id: str, status: ImageStatus | None = None
) -> tuple[str | None, str | None]:
    """Return the ids before and after ``image_id`` in the current filtered order.

    Computed in SQL so stepping through 1,340 images with the arrow keys never
    depends on the client holding the whole list.
    """
    row = conn.execute(
        "SELECT sort_key, filename FROM images WHERE id = ?", (image_id,)
    ).fetchone()
    if row is None:
        raise ImageError(f"no image with id {image_id}")

    key = (str(row["sort_key"]), str(row["filename"]))
    # A nullable parameter carries the optional filter, so the SQL stays a constant
    # string rather than being assembled per call.
    wanted = None if status is None else status.value

    previous = conn.execute(
        "SELECT id FROM images WHERE (sort_key, filename) < (?, ?) "
        "AND (? IS NULL OR status = ?) "
        "ORDER BY sort_key DESC, filename DESC LIMIT 1",
        (*key, wanted, wanted),
    ).fetchone()
    following = conn.execute(
        "SELECT id FROM images WHERE (sort_key, filename) > (?, ?) "
        "AND (? IS NULL OR status = ?) "
        "ORDER BY sort_key, filename LIMIT 1",
        (*key, wanted, wanted),
    ).fetchone()

    return (
        None if previous is None else str(previous["id"]),
        None if following is None else str(following["id"]),
    )
