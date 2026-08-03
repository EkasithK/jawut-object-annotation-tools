"""Label import endpoints.

Import is two calls on purpose. ``preview`` reads the folder and reports what is
there without writing anything; ``apply`` takes the class mapping the user chose
after seeing that report. Doing it in one step would mean guessing where someone
else's class names belong.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jawut import session
from jawut.models import Envelope
from jawut.services import exporter, importer

router = APIRouter(prefix="/api/v1/labels", tags=["labels"])
export_router = APIRouter(prefix="/api/v1/export", tags=["export"])


class PreviewRequest(BaseModel):
    labels_dir: Path


class ApplyRequest(BaseModel):
    labels_dir: Path
    #: Source class index to project class id. ``None`` ignores that class.
    #: JSON object keys are strings, so the index arrives as one.
    class_mapping: dict[str, str | None]
    overwrite: bool = True


@router.post("/preview")
async def preview(payload: PreviewRequest) -> Envelope[importer.LabelPreview]:
    conn = session.require_connection()
    try:
        return Envelope(data=importer.preview(conn, payload.labels_dir))
    except importer.ImporterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=422, detail=f"could not read the folder: {exc}"
        ) from exc


@router.post("/import")
async def apply(payload: ApplyRequest) -> Envelope[importer.LabelImportResult]:
    conn = session.require_connection()

    try:
        mapping = {int(key): value for key, value in payload.class_mapping.items()}
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="class mapping keys must be class indices"
        ) from exc

    try:
        result = importer.apply(
            conn, payload.labels_dir, mapping, overwrite=payload.overwrite
        )
    except importer.ImporterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=422, detail=f"could not read the folder: {exc}"
        ) from exc

    return Envelope(data=result)


@export_router.post("")
async def run_export(
    options: exporter.ExportOptions,
) -> Envelope[exporter.ExportResult]:
    """Write a YOLO dataset to disk.

    Refuses a non-empty destination rather than merging into it: a half-overwritten
    dataset is worse than no dataset, and the failure would only surface at
    training time.
    """
    project = session.require_project()
    conn = session.require_connection()
    try:
        result = exporter.export(conn, project.path, options)
    except exporter.ExporterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"export failed: {exc}") from exc
    return Envelope(data=result)
