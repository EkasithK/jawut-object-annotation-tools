"""Recognise an existing YOLO dataset on disk and turn it into a project.

The three-step route — create a project, add images, import labels — asks someone
to understand the shape of their own data before the tool will help them. Most
people arrive with a folder that a training script wrote and no idea which of the
subfolders matters. So this module reads the folder and reports what is in it,
and :func:`adopt` does the whole job from that one answer.

Nothing here guesses at a class *mapping*. Names come from a ``data.yaml`` and are
created in the order that file declares, so the integer in every ``.txt`` still
means what it meant before — which is the one thing a relabel cannot get wrong.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from jawut.db import connection
from jawut.services import classes, images, importer, projects

#: Subfolder names Ultralytics writes for a split dataset.
SPLIT_NAMES = ("train", "valid", "val", "test")

#: How many images to look at before concluding a folder holds images.
_SCAN_LIMIT = 20_000


class DatasetError(RuntimeError):
    """A folder could not be read as a dataset."""


class DatasetScan(BaseModel):
    """What was found in a folder, in the terms the wizard reports it."""

    root: Path
    #: ``split``, ``images_labels``, ``flat``, ``images_only`` or ``empty``.
    layout: str
    image_dirs: list[Path]
    label_dirs: list[Path]
    image_count: int
    label_count: int
    data_yaml: Path | None
    class_names: list[str]
    #: One sentence naming what was found, shown above the confirm button.
    summary: str


class AdoptResult(BaseModel):
    project: projects.Project
    images_imported: int
    images_skipped: int
    classes_created: int
    boxes_created: int
    images_labeled: int
    #: Images whose label file existed but was empty — a deliberate background,
    #: which is not the same as an image nobody has opened yet.
    images_marked_empty: int
    issues: list[importer.ImportIssue]


def _has_images(folder: Path) -> bool:
    return any(
        path.suffix.lower() in images.IMAGE_EXTENSIONS
        for path in folder.iterdir()
        if path.is_file()
    )


def _count_images(folder: Path) -> int:
    return len(images.scan_folder(folder, recursive=True)[:_SCAN_LIMIT])


def _count_labels(folder: Path) -> int:
    return sum(1 for _ in folder.glob("*.txt"))


def _find_data_yaml(root: Path) -> Path | None:
    """Look for the dataset config at the root, then in any split subfolder.

    ``find_data_yaml`` in the importer searches relative to a *labels* folder;
    this searches relative to the dataset root, which is a different question.
    """
    for name in ("data.yaml", "data.yml", "dataset.yaml", "dataset.yml"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    # Some exports name it after the dataset rather than "data".
    for candidate in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        if candidate.is_file():
            return candidate
    return None


def scan(root: Path) -> DatasetScan:
    """Report what a folder holds without writing anything to it."""
    if not root.is_dir():
        raise DatasetError(f"'{root}' is not a folder")

    image_dirs: list[Path] = []
    label_dirs: list[Path] = []
    layout = "empty"

    split_dirs = [
        root / name for name in SPLIT_NAMES if (root / name / "images").is_dir()
    ]
    if split_dirs:
        layout = "split"
        for split in split_dirs:
            image_dirs.append(split / "images")
            if (split / "labels").is_dir():
                label_dirs.append(split / "labels")
    elif (root / "images").is_dir():
        layout = "images_labels"
        image_dirs.append(root / "images")
        if (root / "labels").is_dir():
            label_dirs.append(root / "labels")
    elif _has_images(root):
        # Images and their .txt files sitting together in one folder.
        layout = "flat"
        image_dirs.append(root)
        if _count_labels(root) > 0:
            label_dirs.append(root)

    image_count = sum(_count_images(folder) for folder in image_dirs)
    label_count = sum(_count_labels(folder) for folder in label_dirs)

    if layout != "empty" and not label_dirs:
        layout = "images_only"

    data_yaml = _find_data_yaml(root)
    class_names: list[str] = []
    if data_yaml is not None:
        try:
            class_names = importer.read_class_names(data_yaml)
        except importer.ImporterError:
            # A yaml that cannot be read is not fatal: the labels still import,
            # the classes just arrive unnamed. Saying so beats refusing.
            data_yaml = None

    return DatasetScan(
        root=root,
        layout=layout,
        image_dirs=image_dirs,
        label_dirs=label_dirs,
        image_count=image_count,
        label_count=label_count,
        data_yaml=data_yaml,
        class_names=class_names,
        summary=_summarise(layout, image_count, label_count, class_names),
    )


def _summarise(
    layout: str, image_count: int, label_count: int, class_names: list[str]
) -> str:
    if layout == "empty" or image_count == 0:
        return "No images found in this folder."
    parts = [f"{image_count:,} images"]
    if label_count:
        parts.append(f"{label_count:,} already labeled")
    else:
        parts.append("no labels yet")
    if class_names:
        parts.append(f"{len(class_names)} classes named in the config")
    return " · ".join(parts)


def adopt(
    parent_dir: Path,
    name: str,
    scanned: DatasetScan,
    copy_images: bool = True,
) -> AdoptResult:
    """Create a project and fill it from a scanned dataset.

    Order matters: images first so labels have something to match by filename,
    then classes in the order ``data.yaml`` declares them, then the labels under
    an identity mapping. Images with no ``.txt`` keep the ``unlabeled`` status
    they were created with — they are *not* marked empty, because nobody has
    looked at them yet, and export treats those two cases differently.
    """
    if scanned.image_count == 0:
        raise DatasetError("there are no images to import in that folder")

    project = projects.create(parent_dir, name)
    conn = connection.connect(project.db_path)

    imported = 0
    skipped = 0
    for folder in scanned.image_dirs:
        result = images.import_folder(
            conn, project.images_dir, folder, recursive=True, copy=copy_images
        )
        imported += result.imported
        skipped += len(result.skipped)

    # Read every label folder before creating anything, so the class list covers
    # indices used by one split but not another. Without this pass a class that
    # only appears in test/ would have nowhere to land and its boxes would be
    # dropped — reported, but still gone.
    previews = {
        folder: importer.preview(conn, folder, scanned.data_yaml)
        for folder in scanned.label_dirs
    }

    names = list(scanned.class_names)
    for preview in previews.values():
        # The preview extends the config's names with class_N placeholders for
        # any higher index, so a longer list is the same list plus the gaps.
        if len(preview.source_classes.names) > len(names):
            names = list(preview.source_classes.names)

    created = [classes.create(conn, class_name) for class_name in names]

    boxes = 0
    labeled = 0
    empty = 0
    issues: list[importer.ImportIssue] = []
    # Index i means the class declared at position i, which is exactly what it
    # meant in the files being read.
    mapping: dict[int, str | None] = {
        index: created[index].id for index in range(len(created))
    }
    for folder in previews:
        applied = importer.apply(conn, folder, mapping, overwrite=True)
        boxes += applied.boxes_created
        labeled += applied.images_labeled
        empty += applied.images_marked_empty
        issues.extend(applied.issues)

    return AdoptResult(
        project=project,
        images_imported=imported,
        images_skipped=skipped,
        classes_created=len(created),
        images_marked_empty=empty,
        boxes_created=boxes,
        images_labeled=labeled,
        issues=issues,
    )
