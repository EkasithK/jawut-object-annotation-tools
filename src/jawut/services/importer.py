"""YOLO label import.

Real label folders are messy: they come from other tools, other class lists, and
half-finished sessions. The rules here are deliberate:

* **Auto-fix only what is unambiguous.** Pixel coordinates and marginal float
  overflow have exactly one sensible reading. Anything else is quarantined and
  reported rather than guessed at.
* **Nothing is ever silently dropped.** Every line that does not become a box
  produces an issue with its file and line number.
* **A missing file and an empty file mean different things.** No label file leaves
  the image ``unlabeled``; an empty one marks it reviewed with no objects.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel

from jawut.services.annotations import MIN_SIDE
from jawut.services.images import ImageStatus
from jawut.util import new_id, now_iso

#: A detection line is `class cx cy w h`. Pose labels from the same family append
#: three fields per keypoint; we keep the box and drop the rest.
DETECTION_FIELDS = 5

#: Above this, a coordinate cannot be normalized and is read as pixels.
PIXEL_THRESHOLD = 1.5

#: Float error from other tools' rounding, silently clamped back into range.
CLAMP_TOLERANCE = 0.02


class IssueKind(StrEnum):
    MALFORMED = "malformed"
    UNKNOWN_CLASS = "unknown_class"
    OUT_OF_RANGE = "out_of_range"
    DEGENERATE = "degenerate"
    UNMATCHED_LABEL = "unmatched_label"
    KEYPOINTS_DROPPED = "keypoints_dropped"
    PIXELS_NORMALIZED = "pixels_normalized"
    COORDS_CLAMPED = "coords_clamped"


#: Issues that describe a repair rather than a rejection.
REPAIRS = frozenset(
    {
        IssueKind.KEYPOINTS_DROPPED,
        IssueKind.PIXELS_NORMALIZED,
        IssueKind.COORDS_CLAMPED,
    }
)


class ImportIssue(BaseModel):
    file: str
    line: int | None
    kind: IssueKind
    detail: str

    @property
    def is_repair(self) -> bool:
        return self.kind in REPAIRS


class ParsedBox(BaseModel):
    source_class: int
    cx: float
    cy: float
    w: float
    h: float


class SourceClasses(BaseModel):
    """Class names found alongside the labels, and where they came from."""

    names: list[str]
    from_data_yaml: bool
    data_yaml_path: str | None = None


class LabelPreview(BaseModel):
    """What a label folder contains, shown before anything is written."""

    label_files: int
    matched_images: int
    unmatched_labels: list[str]
    images_without_labels: int
    source_classes: SourceClasses
    box_counts: dict[int, int]
    issues: list[ImportIssue]


class LabelImportResult(BaseModel):
    images_labeled: int
    boxes_created: int
    images_marked_empty: int
    skipped_boxes: int
    issues: list[ImportIssue]


class ImporterError(RuntimeError):
    """A label import could not proceed at all."""


@dataclass
class _FileParse:
    boxes: list[ParsedBox] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    was_empty: bool = False


def find_data_yaml(folder: Path) -> Path | None:
    """Look for a data.yaml beside the labels, then one level up.

    Exported datasets put it at the root with ``labels/`` beneath, which is why
    the parent is worth checking.
    """
    for candidate in (
        folder / "data.yaml",
        folder / "data.yml",
        folder.parent / "data.yaml",
        folder.parent / "data.yml",
    ):
        if candidate.is_file():
            return candidate
    return None


def read_class_names(data_yaml: Path) -> list[str]:
    """Read ``names`` from a data.yaml, accepting both list and mapping forms."""
    try:
        loaded = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        raise ImporterError(f"could not read {data_yaml.name}: {exc}") from exc

    if not isinstance(loaded, dict) or "names" not in loaded:
        raise ImporterError(f"{data_yaml.name} has no 'names' entry")

    names = loaded["names"]
    if isinstance(names, list):
        return [str(n) for n in names]
    if isinstance(names, dict):
        # Ultralytics also writes {0: 'a', 1: 'b'}; index order is what matters.
        return [str(names[key]) for key in sorted(names, key=lambda k: int(k))]
    raise ImporterError(f"{data_yaml.name} has an unreadable 'names' entry")


def parse_label_file(path: Path, width: int, height: int) -> _FileParse:
    """Parse one YOLO label file against the dimensions of its image."""
    result = _FileParse()

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        result.issues.append(
            ImportIssue(
                file=path.name,
                line=None,
                kind=IssueKind.MALFORMED,
                detail=f"could not read the file: {exc}",
            )
        )
        return result

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        result.was_empty = True
        return result

    for number, raw in enumerate(lines, start=1):
        parsed = _parse_line(path.name, number, raw, width, height)
        box, issues = parsed
        result.issues.extend(issues)
        if box is not None:
            result.boxes.append(box)

    return result


def _parse_line(
    filename: str, number: int, raw: str, width: int, height: int
) -> tuple[ParsedBox | None, list[ImportIssue]]:
    issues: list[ImportIssue] = []

    def problem(kind: IssueKind, detail: str) -> None:
        issues.append(ImportIssue(file=filename, line=number, kind=kind, detail=detail))

    fields = raw.split()
    if len(fields) < DETECTION_FIELDS:
        problem(
            IssueKind.MALFORMED,
            f"expected at least {DETECTION_FIELDS} values, found {len(fields)}",
        )
        return None, issues

    if len(fields) > DETECTION_FIELDS:
        # Pose/segmentation labels from the same family. The box is still valid,
        # and this tool only stores boxes.
        problem(
            IssueKind.KEYPOINTS_DROPPED,
            f"kept the box, dropped {len(fields) - DETECTION_FIELDS} extra values",
        )

    try:
        source_class = int(float(fields[0]))
        cx, cy, w, h = (float(value) for value in fields[1:DETECTION_FIELDS])
    except ValueError:
        problem(IssueKind.MALFORMED, "values are not numeric")
        return None, issues

    if source_class < 0:
        problem(IssueKind.UNKNOWN_CLASS, f"negative class index {source_class}")
        return None, issues

    if w <= 0 or h <= 0:
        problem(IssueKind.DEGENERATE, f"width {w} and height {h} must be positive")
        return None, issues

    # Pixel coordinates: no normalized value can exceed 1 by this much.
    if max(cx, cy, w, h) > PIXEL_THRESHOLD:
        if width <= 0 or height <= 0:
            problem(IssueKind.OUT_OF_RANGE, "cannot normalize without image size")
            return None, issues
        cx, w = cx / width, w / width
        cy, h = cy / height, h / height
        problem(
            IssueKind.PIXELS_NORMALIZED,
            f"read as pixels and divided by {width}x{height}",
        )

    values = {"cx": cx, "cy": cy, "w": w, "h": h}
    over = {
        name: value
        for name, value in values.items()
        if value < -CLAMP_TOLERANCE or value > 1 + CLAMP_TOLERANCE
    }
    if over:
        detail = ", ".join(f"{name}={value:.4f}" for name, value in over.items())
        problem(IssueKind.OUT_OF_RANGE, f"outside 0..1 by more than rounding: {detail}")
        return None, issues

    marginal = any(value < 0 or value > 1 for value in values.values())
    if marginal:
        cx, cy, w, h = (min(1.0, max(0.0, value)) for value in (cx, cy, w, h))
        problem(IssueKind.COORDS_CLAMPED, "nudged back into 0..1")

    # Trim to the frame exactly as the annotation service would on save.
    left, top = max(0.0, cx - w / 2), max(0.0, cy - h / 2)
    right, bottom = min(1.0, cx + w / 2), min(1.0, cy + h / 2)
    trimmed_w, trimmed_h = right - left, bottom - top

    if trimmed_w < MIN_SIDE or trimmed_h < MIN_SIDE:
        problem(IssueKind.DEGENERATE, "box has no area inside the image")
        return None, issues

    return (
        ParsedBox(
            source_class=source_class,
            cx=left + trimmed_w / 2,
            cy=top + trimmed_h / 2,
            w=trimmed_w,
            h=trimmed_h,
        ),
        issues,
    )


def _images_by_stem(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        "SELECT id, filename, width, height, status FROM images"
    ).fetchall()
    return {Path(str(row["filename"])).stem: row for row in rows}


def preview(
    conn: sqlite3.Connection, labels_dir: Path, data_yaml: Path | None = None
) -> LabelPreview:
    """Read a label folder without writing anything.

    Drives the class-mapping step: the user has to see which classes are coming in
    and what shape the files are in before deciding where they land.

    ``data_yaml`` names the class-name source explicitly, for the common case
    where the dataset's yaml is neither beside the labels nor one level up. Left
    unset, :func:`find_data_yaml` looks in those two places.
    """
    if not labels_dir.is_dir():
        raise ImporterError(f"'{labels_dir}' is not a folder")

    label_files = sorted(labels_dir.glob("*.txt"))
    by_stem = _images_by_stem(conn)

    issues: list[ImportIssue] = []
    box_counts: dict[int, int] = {}
    unmatched: list[str] = []
    matched = 0
    highest_class = -1

    for path in label_files:
        image = by_stem.get(path.stem)
        if image is None:
            unmatched.append(path.name)
            issues.append(
                ImportIssue(
                    file=path.name,
                    line=None,
                    kind=IssueKind.UNMATCHED_LABEL,
                    detail="no image in the project has this name",
                )
            )
            continue

        matched += 1
        parsed = parse_label_file(path, int(image["width"]), int(image["height"]))
        issues.extend(parsed.issues)
        for box in parsed.boxes:
            box_counts[box.source_class] = box_counts.get(box.source_class, 0) + 1
            highest_class = max(highest_class, box.source_class)

    chosen_yaml = data_yaml if data_yaml is not None else find_data_yaml(labels_dir)
    if chosen_yaml is not None and not chosen_yaml.is_file():
        raise ImporterError(f"'{chosen_yaml}' is not a file")
    if chosen_yaml is not None:
        try:
            names = read_class_names(chosen_yaml)
            source = SourceClasses(
                names=names, from_data_yaml=True, data_yaml_path=str(chosen_yaml)
            )
        except ImporterError as exc:
            issues.append(
                ImportIssue(
                    file=chosen_yaml.name,
                    line=None,
                    kind=IssueKind.MALFORMED,
                    detail=str(exc),
                )
            )
            source = _placeholder_classes(highest_class)
    else:
        source = _placeholder_classes(highest_class)

    # Indices present in the files but beyond what data.yaml names still need a
    # row in the mapping table, or their boxes would vanish without explanation.
    while len(source.names) <= highest_class:
        source.names.append(f"class_{len(source.names)}")

    return LabelPreview(
        label_files=len(label_files),
        matched_images=matched,
        unmatched_labels=unmatched,
        images_without_labels=len(by_stem) - matched,
        source_classes=source,
        box_counts=box_counts,
        issues=issues,
    )


def _placeholder_classes(highest_class: int) -> SourceClasses:
    return SourceClasses(
        names=[f"class_{i}" for i in range(highest_class + 1)],
        from_data_yaml=False,
    )


def apply(
    conn: sqlite3.Connection,
    labels_dir: Path,
    class_mapping: dict[int, str | None],
    overwrite: bool = True,
) -> LabelImportResult:
    """Write the labels into the project using an explicit class mapping.

    ``class_mapping`` maps each source class index to a project class id, or to
    ``None`` to ignore that class. Indices missing from the mapping are ignored
    too, which is what makes the mapping step meaningful rather than advisory.

    ``overwrite`` replaces existing boxes on a matched image; with it off, images
    that already carry boxes are left alone.
    """
    if not labels_dir.is_dir():
        raise ImporterError(f"'{labels_dir}' is not a folder")

    live = {
        str(row["id"])
        for row in conn.execute(
            "SELECT id FROM classes WHERE deleted_at IS NULL"
        ).fetchall()
    }
    for target in class_mapping.values():
        if target is not None and target not in live:
            raise ImporterError(f"unknown class id in the mapping: {target}")

    by_stem = _images_by_stem(conn)
    issues: list[ImportIssue] = []
    images_labeled = 0
    images_marked_empty = 0
    boxes_created = 0
    skipped_boxes = 0

    try:
        for path in sorted(labels_dir.glob("*.txt")):
            image = by_stem.get(path.stem)
            if image is None:
                continue

            image_id = str(image["id"])
            existing = conn.execute(
                "SELECT COUNT(*) AS n FROM annotations WHERE image_id = ?",
                (image_id,),
            ).fetchone()
            if not overwrite and int(existing["n"]) > 0:
                continue

            parsed = parse_label_file(path, int(image["width"]), int(image["height"]))
            issues.extend(parsed.issues)

            keep: list[tuple[str, ParsedBox]] = []
            for box in parsed.boxes:
                target = class_mapping.get(box.source_class)
                if target is None:
                    skipped_boxes += 1
                    continue
                keep.append((target, box))

            timestamp = now_iso()
            conn.execute("DELETE FROM annotations WHERE image_id = ?", (image_id,))
            for class_id, box in keep:
                conn.execute(
                    "INSERT INTO annotations (id, image_id, class_id, cx, cy, w, h, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id(),
                        image_id,
                        class_id,
                        box.cx,
                        box.cy,
                        box.w,
                        box.h,
                        timestamp,
                        timestamp,
                    ),
                )

            if keep:
                status = ImageStatus.IN_PROGRESS
                images_labeled += 1
                boxes_created += len(keep)
            elif parsed.was_empty:
                # An empty file is a statement: reviewed, nothing here.
                status = ImageStatus.DONE
                images_marked_empty += 1
            else:
                # Every box was ignored or rejected, so the image still needs a look.
                status = ImageStatus.NEEDS_REVIEW

            conn.execute(
                "UPDATE images SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, timestamp, image_id),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return LabelImportResult(
        images_labeled=images_labeled,
        boxes_created=boxes_created,
        images_marked_empty=images_marked_empty,
        skipped_boxes=skipped_boxes,
        issues=issues,
    )
