"""Endpoints behind "Open existing dataset".

Two calls, for the same reason label import is two calls: ``scan`` reports what a
folder holds and writes nothing, and ``adopt`` acts on what the user saw. Nobody
is asked to confirm an import they have not been shown.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from jawut import config, session
from jawut.models import Envelope
from jawut.routers.projects import ProjectSummary
from jawut.services import classes, dataset, importer, projects

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


class ScanRequest(BaseModel):
    path: Path


class AdoptRequest(BaseModel):
    path: Path
    name: str = Field(min_length=1, max_length=100)
    parent_dir: Path
    copy_images: bool = True


class AdoptResponse(BaseModel):
    project: ProjectSummary
    images_imported: int
    images_skipped: int
    classes_created: int
    boxes_created: int
    images_labeled: int
    images_marked_empty: int
    issues: list[dict[str, object]]


@router.post("/scan")
async def scan(payload: ScanRequest) -> Envelope[dataset.DatasetScan]:
    try:
        return Envelope(data=dataset.scan(payload.path))
    except dataset.DatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=422, detail=f"could not read the folder: {exc}"
        ) from exc


@router.post("/adopt", status_code=201)
async def adopt(payload: AdoptRequest) -> Envelope[AdoptResponse]:
    """Create a project from a dataset folder and import everything in it."""
    try:
        scanned = dataset.scan(payload.path)
        result = dataset.adopt(
            payload.parent_dir, payload.name, scanned, copy_images=payload.copy_images
        )
    except (
        dataset.DatasetError,
        projects.ProjectError,
        classes.ClassError,
        importer.ImporterError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=422, detail=f"could not build the project: {exc}"
        ) from exc

    session.set_current(result.project)
    config.remember_project(result.project.name, result.project.path)

    return Envelope(
        data=AdoptResponse(
            project=ProjectSummary.of(result.project),
            images_imported=result.images_imported,
            images_skipped=result.images_skipped,
            classes_created=result.classes_created,
            boxes_created=result.boxes_created,
            images_labeled=result.images_labeled,
            images_marked_empty=result.images_marked_empty,
            issues=[issue.model_dump(mode="json") for issue in result.issues],
        )
    )
