"""Bounding box endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jawut import session
from jawut.models import Envelope
from jawut.services import annotations as ann
from jawut.services import images

router = APIRouter(prefix="/api/v1/annotations", tags=["annotations"])


class SaveRequest(BaseModel):
    """The complete set of boxes for one image.

    An empty list is a valid, meaningful save: the image was reviewed and contains
    no objects.
    """

    boxes: list[ann.Box]
    status: images.ImageStatus | None = None


class SaveResult(BaseModel):
    boxes: list[ann.StoredBox]
    image: images.ImageRecord


class ReassignRequest(BaseModel):
    from_class: str
    to_class: str


class ReassignResult(BaseModel):
    moved: int


def _fail(exc: ann.AnnotationError) -> HTTPException:
    message = str(exc)
    status = 404 if message.startswith("no image with id") else 422
    return HTTPException(status_code=status, detail=message)


@router.get("/{image_id}")
async def list_for_image(image_id: str) -> Envelope[list[ann.StoredBox]]:
    conn = session.require_connection()
    return Envelope(data=ann.list_for_image(conn, image_id))


@router.put("/{image_id}")
async def save(image_id: str, payload: SaveRequest) -> Envelope[SaveResult]:
    conn = session.require_connection()
    try:
        boxes = ann.replace_for_image(conn, image_id, payload.boxes, payload.status)
    except ann.AnnotationError as exc:
        raise _fail(exc) from exc

    return Envelope(data=SaveResult(boxes=boxes, image=images.get(conn, image_id)))


@router.post("/reassign")
async def reassign(payload: ReassignRequest) -> Envelope[ReassignResult]:
    """Move every box of one class to another across the whole project."""
    conn = session.require_connection()
    try:
        moved = ann.reassign_class(conn, payload.from_class, payload.to_class)
    except ann.AnnotationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Envelope(data=ReassignResult(moved=moved))
