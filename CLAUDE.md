# Jawut Object Annotation Tools — project configuration

Extends the root `Kowz_Project/CLAUDE.md`. Everything there applies unless overridden below.

## What this is

A standalone Windows desktop application for bounding-box object detection labeling, exporting
YOLO datasets. It runs as a local FastAPI server inside a native window — there is no hosted
component, no external service, and no ML dependency.

## Overrides of the root standards

These deviations are deliberate; the reasoning is in `.dev/DECISIONS.md`.

| Root standard | Here | Reason |
|---|---|---|
| Next.js 14+ (App Router) | Vite + React + TypeScript | Next.js needs a Node server, which cannot be bundled into a Windows exe. Vite emits static assets FastAPI can serve. |
| PostgreSQL + SQLAlchemy async + Alembic | SQLite via stdlib `sqlite3`, `PRAGMA user_version` migrations | Single-user desktop app; one `project.db` per project. `sqlite3` is stdlib so it adds nothing to the bundle. |
| Integration tests hit real services via Docker Compose | Integration tests use a real SQLite file in `tmp_path` | SQLite *is* the real dependency. Nothing is mocked — the rule's intent is preserved. |
| Docker multi-stage build, ECS/Terraform/AWS | PyInstaller `onedir` + GitHub Release | Nothing is hosted. |
| JWT auth, rate limiting, CORS whitelist | Loopback-only bind plus a random per-launch token | Server binds `127.0.0.1` on an OS-assigned port and exits with the window. |
| All routes `async def` | `async def` routes, synchronous `sqlite3` calls inside them | SQLite operations here are sub-millisecond local file I/O; an async driver would add a dependency for no gain. |

Everything else — ruff at line length 88, mypy strict, full type annotations, Pydantic v2 at every
API boundary, 80% coverage, Conventional Commits, `.env.example` discipline — holds as written.

## Authorship

Per the root standard: **no AI attribution anywhere**. No `Co-Authored-By` trailers, no "generated
by" notes, no AI signatures in code, comments, docstrings, or docs. Commit messages are plain
Conventional Commits and have been kept clean from the first commit, so this repository never
needs a history rewrite before going public.

Development-only tracking (`.dev/`) is committed on purpose so work carries between machines, and
is removed in a single commit when the repo goes public — see `.dev/PRE_PUBLIC_CHECKLIST.md`.

## Working here

Read `.dev/STATUS.md` first — it holds what is in progress, what is next, and environment notes.
`.dev/PLAN.md` is the durable spec and phase checklist. Log any scope change in
`.dev/DECISIONS.md` with its reason.

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
