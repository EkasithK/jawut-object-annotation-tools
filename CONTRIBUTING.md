# Contributing

Jawut is a standalone Windows desktop application for bounding-box labeling that exports YOLO
datasets. It runs as a local FastAPI server inside a native window — no hosted component, no
external service, no ML dependency. This file records the design choices and the rules that are
easy to get wrong, so contributions keep them intact.

## Design choices

| Choice | Why |
|---|---|
| Vite + React + TypeScript frontend, served as static assets by FastAPI | A Node server cannot be bundled into a Windows executable; static assets can |
| SQLite through the standard-library `sqlite3`, migrations by `PRAGMA user_version` | Single-user desktop app, one `project.db` per project; stdlib adds nothing to the bundle |
| Integration tests use a real SQLite file in `tmp_path` | SQLite *is* the real dependency; nothing is mocked |
| PyInstaller `onedir` bundle, published as a GitHub Release | Nothing is hosted |
| Loopback-only bind plus a random per-launch token | The server binds `127.0.0.1` on an OS-assigned port and exits with the window |
| `async def` routes with synchronous `sqlite3` calls inside | Local file I/O is sub-millisecond; an async driver would add a dependency for no gain |

Code standards: ruff at line length 88, mypy strict, full type annotations, Pydantic v2 at every
API boundary, 80% test coverage, Conventional Commits.

## Domain rules that are easy to get wrong

- **A missing `.txt` and an empty `.txt` mean different things.** Missing means nobody has looked
  at the image; empty means someone looked and there are genuinely no objects — a valid background
  image. That distinction is carried by `images.status`, and export depends on it.
- **Never assign a class its YOLO integer before export.** Classes carry stable UUIDs; the
  contiguous index is derived from `order_index` at export time. This is what makes deleting a
  class safe.
- **Never silently drop a malformed label line on import.** Auto-fix only what is unambiguous
  (pixel coordinates, marginal overflow); quarantine everything else and surface it in the import
  report.
- **All box coordinates are normalized `[0,1]` center-form (`cx cy w h`)** everywhere in the
  database and the API. Pixel coordinates exist only inside the canvas view transform.

## Commands

```bash
uv sync                          # install dependencies
uv run uvicorn jawut.app:app --reload --port 8000
cd frontend && npm run dev       # Vite dev server, proxies /api to :8000

uv run ruff check . && uv run ruff format --check .
uv run mypy src/
uv run pytest tests/ -v --cov=src --cov-report=term-missing
```

## Submitting changes

Open a pull request against `main` with a Conventional Commit title (`feat(canvas): …`,
`fix(export): …`). CI runs lint, types, tests and the Windows build; all must pass.
