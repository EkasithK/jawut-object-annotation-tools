"""Image import, listing, navigation and byte serving."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from jawut import session
from jawut.models import Envelope
from jawut.services import annotations as ann
from jawut.services import images as img

router = APIRouter(prefix="/api/v1/images", tags=["images"])


class ImportRequest(BaseModel):
    source: Path
    recursive: bool = True
    # Not named `copy`: that shadows a BaseModel method.
    copy_into_project: bool = True


class ImageList(BaseModel):
    images: list[img.ImageRecord]
    counts: img.StatusCounts


class ImageDetail(BaseModel):
    """One image with everything the canvas needs to render it."""

    image: img.ImageRecord
    boxes: list[ann.StoredBox]
    previous_id: str | None
    next_id: str | None


class StatusRequest(BaseModel):
    status: img.ImageStatus


def _fail(exc: img.ImageError) -> HTTPException:
    message = str(exc)
    status = 404 if message.startswith("no image with id") else 422
    return HTTPException(status_code=status, detail=message)


@router.post("/import", status_code=201)
async def import_folder(payload: ImportRequest) -> Envelope[img.ImportResult]:
    project = session.require_project()
    conn = session.require_connection()
    try:
        result = img.import_folder(
            conn,
            project.images_dir,
            payload.source,
            recursive=payload.recursive,
            copy=payload.copy_into_project,
        )
    except img.ImageError as exc:
        raise _fail(exc) from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"import failed: {exc}") from exc
    return Envelope(data=result)


@router.get("")
async def list_all(
    status: img.ImageStatus | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> Envelope[ImageList]:
    conn = session.require_connection()
    return Envelope(
        data=ImageList(
            images=img.list_images(conn, status, limit, offset),
            counts=img.counts(conn),
        )
    )


@router.get("/{image_id}")
async def detail(
    image_id: str, status: img.ImageStatus | None = None
) -> Envelope[ImageDetail]:
    """One image plus its boxes and its neighbours under the active filter."""
    conn = session.require_connection()
    try:
        record = img.get(conn, image_id)
        previous_id, next_id = img.neighbours(conn, image_id, status)
    except img.ImageError as exc:
        raise _fail(exc) from exc

    return Envelope(
        data=ImageDetail(
            image=record,
            boxes=ann.list_for_image(conn, image_id),
            previous_id=previous_id,
            next_id=next_id,
        )
    )


@router.get("/{image_id}/file")
async def file(image_id: str) -> FileResponse:
    """Serve the image bytes.

    A linked image can vanish or become unreadable between imports, which is a
    normal condition rather than a server fault — report it as a missing resource.
    """
    project = session.require_project()
    conn = session.require_connection()
    try:
        path = img.resolve_path(conn, image_id, project.path)
    except img.ImageError as exc:
        raise _fail(exc) from exc

    if not path.is_file():
        raise HTTPException(
            status_code=404, detail=f"the image file is missing from {path}"
        )
    return FileResponse(path)


@router.patch("/{image_id}/status")
async def set_status(
    image_id: str, payload: StatusRequest
) -> Envelope[img.ImageRecord]:
    conn = session.require_connection()
    try:
        return Envelope(data=img.set_status(conn, image_id, payload.status))
    except img.ImageError as exc:
        raise _fail(exc) from exc
