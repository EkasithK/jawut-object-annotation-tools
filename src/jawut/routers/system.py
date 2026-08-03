"""Native dialog endpoints.

These exist so the frontend can offer a Browse button instead of asking someone
to type a Windows path. They only do anything when the app is running inside its
desktop window, which is why the frontend asks :func:`capabilities` first and
falls back to the typed field when the answer is no.
"""

from __future__ import annotations

from anyio import to_thread
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jawut import desktop
from jawut.models import Envelope

router = APIRouter(prefix="/api/v1/system", tags=["system"])

# Presented in the file chooser's type filter. pywebview expects this exact shape.
DATA_YAML_TYPES = ("Dataset config (*.yaml;*.yml)", "All files (*.*)")


class Capabilities(BaseModel):
    native_dialogs: bool


class BrowseRequest(BaseModel):
    """``start_in`` is a hint only — a path that no longer exists is ignored."""

    kind: str = "folder"
    start_in: str = ""


class BrowseResult(BaseModel):
    """``path`` is ``None`` when the dialog was cancelled, which is not an error."""

    path: str | None


@router.get("/capabilities")
async def capabilities() -> Envelope[Capabilities]:
    return Envelope(data=Capabilities(native_dialogs=desktop.is_available()))


@router.post("/browse")
async def browse(payload: BrowseRequest) -> Envelope[BrowseResult]:
    if payload.kind not in ("folder", "data_yaml"):
        raise HTTPException(status_code=422, detail=f"unknown kind: {payload.kind}")
    if not desktop.is_available():
        raise HTTPException(
            status_code=409,
            detail="native dialogs need the desktop window; type the path instead",
        )

    # The dialog blocks until the user answers it, so it cannot run on the event
    # loop — every other request would stall behind it.
    try:
        if payload.kind == "folder":
            chosen = await to_thread.run_sync(desktop.pick_folder, payload.start_in)
        else:
            chosen = await to_thread.run_sync(
                desktop.pick_file, payload.start_in, DATA_YAML_TYPES
            )
    except Exception as exc:  # noqa: BLE001  the backend raises platform-specific errors
        raise HTTPException(
            status_code=500, detail=f"the file dialog failed: {exc}"
        ) from exc

    return Envelope(data=BrowseResult(path=chosen))
