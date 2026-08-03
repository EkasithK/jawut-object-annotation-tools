"""Class management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from jawut import session
from jawut.models import Envelope
from jawut.services import classes

router = APIRouter(prefix="/api/v1/classes", tags=["classes"])


class ClassList(BaseModel):
    classes: list[classes.ObjectClass]


class CreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str | None = None


class UpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = None


class ReorderRequest(BaseModel):
    ordered_ids: list[str]


class DeleteRequest(BaseModel):
    """``reassign_to`` moves the existing boxes; omitting it deletes them."""

    reassign_to: str | None = None


class DeleteResult(BaseModel):
    deleted: classes.ClassUsage
    reassigned_to: str | None
    classes: list[classes.ObjectClass]


def _fail(exc: classes.ClassError) -> HTTPException:
    message = str(exc)
    status = 404 if message.startswith("no class with id") else 422
    return HTTPException(status_code=status, detail=message)


@router.get("")
async def list_all() -> Envelope[ClassList]:
    conn = session.require_connection()
    return Envelope(data=ClassList(classes=classes.list_classes(conn)))


@router.post("", status_code=201)
async def create(payload: CreateRequest) -> Envelope[classes.ObjectClass]:
    conn = session.require_connection()
    try:
        return Envelope(data=classes.create(conn, payload.name, payload.color))
    except classes.ClassError as exc:
        raise _fail(exc) from exc


@router.patch("/{class_id}")
async def update(
    class_id: str, payload: UpdateRequest
) -> Envelope[classes.ObjectClass]:
    conn = session.require_connection()
    try:
        return Envelope(
            data=classes.update(conn, class_id, payload.name, payload.color)
        )
    except classes.ClassError as exc:
        raise _fail(exc) from exc


@router.post("/reorder")
async def reorder(payload: ReorderRequest) -> Envelope[ClassList]:
    conn = session.require_connection()
    try:
        ordered = classes.reorder(conn, payload.ordered_ids)
    except classes.ClassError as exc:
        raise _fail(exc) from exc
    return Envelope(data=ClassList(classes=ordered))


@router.get("/{class_id}/usage")
async def usage(class_id: str) -> Envelope[classes.ClassUsage]:
    """What a delete would affect. The confirmation dialog calls this first."""
    conn = session.require_connection()
    try:
        return Envelope(data=classes.usage(conn, class_id))
    except classes.ClassError as exc:
        raise _fail(exc) from exc


@router.post("/{class_id}/delete")
async def delete(class_id: str, payload: DeleteRequest) -> Envelope[DeleteResult]:
    """Delete a class, reassigning or removing the boxes that used it.

    Modelled as POST rather than DELETE because it carries a body: the choice
    between reassigning and discarding is the whole decision.
    """
    conn = session.require_connection()
    try:
        removed = classes.delete(conn, class_id, payload.reassign_to)
    except classes.ClassError as exc:
        raise _fail(exc) from exc

    return Envelope(
        data=DeleteResult(
            deleted=removed,
            reassigned_to=payload.reassign_to,
            classes=classes.list_classes(conn),
        )
    )
