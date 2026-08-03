"""FastAPI application factory.

The server is bound to loopback and lives for exactly as long as the desktop window,
so there is no auth layer beyond the per-launch token checked in
:func:`require_launch_token`. That token is what stops another process on the same
machine from finding the port and driving the API; nothing off the machine can
reach it at all.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from jawut import APP_NAME, __version__
from jawut.models import Envelope, ErrorDetail, HealthStatus, ReadyStatus
from jawut.resources import package_file
from jawut.routers.annotations import router as annotations_router
from jawut.routers.classes import router as classes_router
from jawut.routers.datasets import router as datasets_router
from jawut.routers.images import router as images_router
from jawut.routers.io import export_router
from jawut.routers.io import router as io_router
from jawut.routers.projects import router as projects_router
from jawut.routers.system import router as system_router
from jawut.session import NoProjectOpenError

LAUNCH_TOKEN_ENV = "JAWUT_LAUNCH_TOKEN"  # noqa: S105  variable name, not a secret
LAUNCH_TOKEN_HEADER = "X-Jawut-Token"  # noqa: S105  header name, not a secret


STATIC_DIR = package_file("static")


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

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        """Serve the app shell with the launch token already in it.

        Injecting the token here rather than after the window opens removes a
        race: the page can otherwise issue its first request before an
        ``evaluate_js`` call has run, and that request would be rejected.
        """
        page = STATIC_DIR / "index.html"
        if not page.is_file():
            raise HTTPException(
                status_code=404,
                detail=(
                    "the frontend is not built — run `npm --prefix frontend run build`"
                ),
            )

        html = page.read_text(encoding="utf-8")
        token = os.environ.get(LAUNCH_TOKEN_ENV)
        if token:
            script = f"<script>window.__JAWUT_TOKEN__={json.dumps(token)};</script>"
            html = html.replace("</head>", f"{script}</head>", 1)
        return HTMLResponse(html)

    guarded = [Depends(require_launch_token)]
    for api_router in (
        projects_router,
        classes_router,
        images_router,
        annotations_router,
        io_router,
        export_router,
        system_router,
        datasets_router,
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
