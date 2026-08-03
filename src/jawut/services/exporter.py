"""YOLO dataset export.

This is the only place a class acquires an integer. Indices are derived from
``order_index`` over live classes at the moment of export and stored nowhere, which
is what makes deleting and reordering classes safe everywhere else.

Two layouts are offered:

* **split** — ``train/`` ``val/`` ``test/``, stratified and seeded, ready to train
* **flat** — one ``images/`` and ``labels/`` pair, for splitting by hand later

An image reviewed as containing nothing exports an **empty** ``.txt``: a valid
background image. An image nobody has opened is excluded by default, because
exporting it as an empty label would teach the model it is a background.
"""

from __future__ import annotations

import json
import random
import shutil
import sqlite3
from collections import defaultdict
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from jawut.services import classes as class_service
from jawut.services.images import ImageStatus, resolve_path
from jawut.util import now_iso

DEFAULT_SEED = 42
SPLIT_NAMES = ("train", "val", "test")

#: Coordinates are written at this precision, matching what Ultralytics emits.
COORD_PRECISION = 6


class ExportLayout(StrEnum):
    SPLIT = "split"
    FLAT = "flat"


class ExporterError(RuntimeError):
    """An export could not be produced."""


class SplitRatios(BaseModel):
    train: float = Field(default=0.70, ge=0.0, le=1.0)
    val: float = Field(default=0.15, ge=0.0, le=1.0)
    test: float = Field(default=0.15, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _must_sum_to_one(self) -> SplitRatios:
        total = self.train + self.val + self.test
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"split ratios must sum to 1.0, got {total}")
        return self


class ExportOptions(BaseModel):
    destination: Path
    layout: ExportLayout = ExportLayout.SPLIT
    ratios: SplitRatios = Field(default_factory=SplitRatios)
    seed: int = DEFAULT_SEED
    #: Untouched images are excluded by default: exporting them as empty labels
    #: would assert they contain no objects, which nobody has checked.
    include_unlabeled: bool = False
    copy_images: bool = True


class ExportResult(BaseModel):
    destination: Path
    layout: ExportLayout
    class_names: list[str]
    images_exported: int
    boxes_exported: int
    empty_labels: int
    counts_per_split: dict[str, int]
    data_yaml: Path
    manifest: Path


class _ExportImage(BaseModel):
    id: str
    filename: str
    status: ImageStatus
    class_ids: list[str]


def _format_line(index: int, cx: float, cy: float, w: float, h: float) -> str:
    values = " ".join(f"{v:.{COORD_PRECISION}f}" for v in (cx, cy, w, h))
    return f"{index} {values}"


def _collect(conn: sqlite3.Connection, include_unlabeled: bool) -> list[_ExportImage]:
    rows = conn.execute(
        "SELECT id, filename, status FROM images ORDER BY sort_key, filename"
    ).fetchall()

    boxes_by_image: dict[str, list[str]] = defaultdict(list)
    for row in conn.execute("SELECT image_id, class_id FROM annotations").fetchall():
        boxes_by_image[str(row["image_id"])].append(str(row["class_id"]))

    selected = []
    for row in rows:
        status = ImageStatus(str(row["status"]))
        if status is ImageStatus.UNLABELED and not include_unlabeled:
            continue
        selected.append(
            _ExportImage(
                id=str(row["id"]),
                filename=str(row["filename"]),
                status=status,
                class_ids=boxes_by_image.get(str(row["id"]), []),
            )
        )
    return selected


def _stratum(image: _ExportImage, frequency: dict[str, int]) -> str:
    """Group images by the rarest class they contain.

    Detection images carry several classes at once, so there is no single label to
    stratify on. Keying on the rarest present class is the practical stand-in: it
    keeps a scarce class like ``Helmet_Ngob`` from landing entirely in one split,
    which is exactly the failure that makes validation numbers meaningless.
    """
    if not image.class_ids:
        return "__background__"
    return min(set(image.class_ids), key=lambda c: (frequency.get(c, 0), c))


def assign_splits(
    images: list[_ExportImage], ratios: SplitRatios, seed: int
) -> dict[str, str]:
    """Map image id to split name, stratified and reproducible for a given seed."""
    frequency: dict[str, int] = defaultdict(int)
    for image in images:
        for class_id in set(image.class_ids):
            frequency[class_id] += 1

    grouped: dict[str, list[_ExportImage]] = defaultdict(list)
    for image in images:
        grouped[_stratum(image, frequency)].append(image)

    rng = random.Random(seed)  # noqa: S311  reproducible splitting, not cryptography
    assignment: dict[str, str] = {}

    for stratum in sorted(grouped):
        members = sorted(grouped[stratum], key=lambda i: i.filename)
        rng.shuffle(members)

        total = len(members)
        train_end = round(total * ratios.train)
        val_end = train_end + round(total * ratios.val)

        for position, image in enumerate(members):
            if position < train_end:
                assignment[image.id] = "train"
            elif position < val_end:
                assignment[image.id] = "val"
            else:
                assignment[image.id] = "test"

    return assignment


def _write_data_yaml(
    destination: Path, class_names: list[str], layout: ExportLayout
) -> Path:
    """Write data.yaml in the same shape Ultralytics reads and writes."""
    document: dict[str, object] = {"path": str(destination.resolve())}

    if layout is ExportLayout.SPLIT:
        for split in SPLIT_NAMES:
            document[split] = f"{split}/images"
    else:
        document["train"] = "images"
        document["val"] = "images"

    document["nc"] = len(class_names)
    document["names"] = class_names

    path = destination / "data.yaml"
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def export(
    conn: sqlite3.Connection, project_dir: Path, options: ExportOptions
) -> ExportResult:
    """Write a YOLO dataset to ``options.destination``."""
    live_classes = class_service.list_classes(conn)
    if not live_classes:
        raise ExporterError("the project has no classes to export")

    index_map = class_service.export_index_map(conn)
    class_names = [cls.name for cls in live_classes]

    selected = _collect(conn, options.include_unlabeled)
    if not selected:
        raise ExporterError(
            "no images to export — label some images, or include unlabeled ones"
        )

    destination = options.destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ExporterError(f"'{destination}' already exists and is not empty")

    if options.layout is ExportLayout.SPLIT:
        assignment = assign_splits(selected, options.ratios, options.seed)
        split_dirs = {
            split: (destination / split / "images", destination / split / "labels")
            for split in SPLIT_NAMES
        }
    else:
        assignment = {image.id: "all" for image in selected}
        split_dirs = {"all": (destination / "images", destination / "labels")}

    for image_dir, label_dir in split_dirs.values():
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)

    boxes_exported = 0
    empty_labels = 0
    counts: dict[str, int] = {split: 0 for split in split_dirs}
    manifest_images: list[dict[str, object]] = []

    for image in selected:
        split = assignment[image.id]
        image_dir, label_dir = split_dirs[split]

        source = resolve_path(conn, image.id, project_dir)
        if not source.is_file():
            raise ExporterError(f"the image file for {image.filename} is missing")

        if options.copy_images:
            shutil.copy2(source, image_dir / image.filename)

        rows = conn.execute(
            "SELECT class_id, cx, cy, w, h FROM annotations WHERE image_id = ? "
            "ORDER BY created_at, id",
            (image.id,),
        ).fetchall()

        lines = [
            _format_line(
                index_map[str(row["class_id"])],
                float(row["cx"]),
                float(row["cy"]),
                float(row["w"]),
                float(row["h"]),
            )
            for row in rows
            if str(row["class_id"]) in index_map
        ]

        label_path = label_dir / f"{Path(image.filename).stem}.txt"
        # An empty file is written deliberately: it declares a background image.
        label_path.write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )

        boxes_exported += len(lines)
        if not lines:
            empty_labels += 1
        counts[split] += 1
        manifest_images.append(
            {
                "filename": image.filename,
                "split": split,
                "boxes": len(lines),
                "status": image.status.value,
            }
        )

    data_yaml = _write_data_yaml(destination, class_names, options.layout)

    manifest_path = destination / "export_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "exported_at": now_iso(),
                "layout": options.layout.value,
                "seed": options.seed,
                "ratios": options.ratios.model_dump(),
                "include_unlabeled": options.include_unlabeled,
                "classes": [
                    {"index": index_map[cls.id], "name": cls.name, "id": cls.id}
                    for cls in live_classes
                ],
                "counts_per_split": counts,
                "images": manifest_images,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return ExportResult(
        destination=destination,
        layout=options.layout,
        class_names=class_names,
        images_exported=len(selected),
        boxes_exported=boxes_exported,
        empty_labels=empty_labels,
        counts_per_split=counts,
        data_yaml=data_yaml,
        manifest=manifest_path,
    )
