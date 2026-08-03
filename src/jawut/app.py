"""FastAPI application factory.

The server is bound to loopback and lives for exactly as long as the desktop window,
so there is no auth layer beyond the per-launch token checked in
:func:`require_launch_token`. See ``CLAUDE.md`` for why that is sufficient here.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from jawut import APP_NAME, __version__
from jawut.models import Envelope, ErrorDetail, HealthStatus, ReadyStatus
from jawut.routers.annotations import router as annotations_router
from jawut.routers.classes import router as classes_router
from jawut.routers.images import router as images_router
from jawut.routers.projects import router as projects_router
from jawut.session import NoProjectOpenError

LAUNCH_TOKEN_ENV = "JAWUT_LAUNCH_TOKEN"  # noqa: S105  variable name, not a secret
LAUNCH_TOKEN_HEADER = "X-Jawut-Token"  # noqa: S105  header name, not a secret

STATIC_DIR = Path(__file__).resolve().parent / "static"


def require_launch_token(
    x_jawut_token: str | None = Header(default=None, alias=LAUNCH_TOKEN_HEADER),
) -> None:
    """Reject calls from other local processes that guessed the port.

    No token in the environment means development, where the check is skipped.
    """
    expected = os.environ.get(LAUNCH_TOKEN_ENV)
    if not expected:
        return
    if x_jawut_token != expected:
        raise HTTPException(status_code=401, detail="invalid launch token")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    from jawut.db.connection import close_all

    close_all()


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        lifespan=lifespan,
    )

    # Registered on the Starlette class so that router-level 404s, which never pass
    # through FastAPI's subclass, are enveloped too.
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        envelope: Envelope[None] = Envelope(
            error=ErrorDetail(code=_code_for(exc.status_code), message=str(exc.detail))
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(mode="json"),
        )

    @app.get("/health")
    async def health() -> Envelope[HealthStatus]:
        return Envelope(data=HealthStatus(status="ok", version=__version__))

    @app.exception_handler(NoProjectOpenError)
    async def no_project_handler(
        request: Request, exc: NoProjectOpenError
    ) -> JSONResponse:
        envelope: Envelope[None] = Envelope(
            error=ErrorDetail(code="NO_PROJECT_OPEN", message=str(exc))
        )
        return JSONResponse(status_code=409, content=envelope.model_dump(mode="json"))

    @app.get("/ready")
    async def ready() -> Envelope[ReadyStatus]:
        from jawut.db.connection import probe

        return Envelope(data=ReadyStatus(db=probe()))

    guarded = [Depends(require_launch_token)]
    for api_router in (
        projects_router,
        classes_router,
        images_router,
        annotations_router,
    ):
        app.include_router(api_router, dependencies=guarded)

    # Mounted last so it cannot shadow the API routes above.
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


def _code_for(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
    }.get(status_code, "INTERNAL_ERROR")


app = create_app()
