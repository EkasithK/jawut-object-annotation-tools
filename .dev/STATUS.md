# Status — 2026-08-03

## Now

Phases 1 and 2 complete and pushed; CI green. Ready to start Phase 3 — image import and
the labeling canvas.

## Done

- **Planning** — scope, storage model, packaging approach and phases agreed. `PLAN.md` is the
  spec, `DECISIONS.md` records why each choice was made.
- **Phase 1 — Skeleton**
  - `pyproject.toml` (uv, ruff, mypy strict, pytest), `.pre-commit-config.yaml`, `.gitignore`,
    `.env.example`, sub-project `CLAUDE.md`, `README.md`
  - `.github/workflows/ci.yml` — backend lint/format/typecheck/test, frontend
    lint/typecheck/build, security scan (pip-audit on the exported lockfile + trivy)
  - Private repo `EkasithK/jawut-object-annotation-tools` created and pushed
- **Phase 2 — Core**
  - `db/schema.sql` v1: meta, classes, images, annotations, edit_log. `STRICT` tables, CHECK
    constraints on coordinates and status, cascade from images to annotations, FK block on
    deleting a class still in use, partial unique index so a deleted class name can be reused.
  - `db/migrations.py` — `PRAGMA user_version` runner, transactional, refuses a database from a
    newer build rather than downgrading it.
  - `config.py` — per-user app data directory (Windows/macOS/Linux), atomic settings write,
    recent-projects list that survives a corrupt file.
  - `services/projects.py` — create/open/close, Windows path-name rules enforced on every
    platform, refuses to scatter project files into a non-empty directory.
  - `session.py` — the single open project; routers reach it via `require_connection`.
  - `routers/projects.py` — `GET /api/v1/projects` returns the whole welcome state in one call;
    create, open, close, forget.
  - Welcome screen: bounding-box corner brackets and a label chip as the visual grammar, signal
    orange accent, monospace for paths.
- 100 tests passing, 96% backend coverage, `ruff` and `mypy --strict` clean, frontend builds.
- Verified end to end against a running server: create project → directory, `project.db` and
  `images/` on disk → recorded in recents → SPA served from `src/jawut/static/`.

## Next

Phase 3, in this order:

1. `services/images.py` — folder import, Pillow dimensions, sha256 dedupe, copy-into-project vs
   link-in-place, natural sort key
2. Images router: list with status filter, serve image bytes, update status
3. `services/classes.py` + router — CRUD, and the delete flow that counts usage then reassigns or
   deletes in one transaction
4. `BoxCanvas.tsx` — fit/zoom/pan first, then draw and resize with edge handles
5. Annotations router + optimistic client state
6. Keybindings and the status filter bar
7. Undo/redo on `edit_log`

## Open questions / blocked

- None.

## Notes for the next session

- Toolchain: `uv` venv resolves to Python 3.11.15, node 24.16. Code targets py311 so the Windows
  CI build stays compatible.
- Dev runs two processes: `uv run uvicorn jawut.app:app --reload --port 8000` and
  `cd frontend && npm run dev` (Vite proxies `/api`, `/health`, `/ready` to :8000). Set
  `JAWUT_APP_DATA_DIR` to a scratch path when testing so real settings are not touched.
- `app.py` registers its error handler on **Starlette's** `HTTPException`, not FastAPI's subclass.
  Router-level 404s never pass through the subclass, so registering on the subclass silently
  breaks the response envelope. Do not "simplify" that import.
- `StaticFiles` is mounted at `/` **after** the routers, and only when `src/jawut/static/` exists.
  Once client-side routing lands, that mount needs an index.html fallback for unknown paths.
- CI gotchas already hit: `aquasecurity/trivy-action` tags are `v`-prefixed, and `pip-audit`
  cannot audit the installed environment because `jawut` is unpublished — the workflow audits
  `uv export --no-emit-project` output instead.
- Reference code for Phase 3: the old labeler at
  `../ekasith-phd-thesis/experiments/tools/labeler/` — `static/index.html:262-274` has the
  image↔canvas view transform (`fitView`, `toC`, `toI`, `nToImg`, `imgToN`) worth porting into
  `BoxCanvas.tsx` rather than re-deriving. `app.py:81-90` is the backup-original-once pattern the
  `edit_log` table replaces.
- Real data for Phase 7: `../helmet_ngob_reject/Data/` (`data.yaml` is 2-class); the 4-class
  taxonomy and labeling rules are in `../helmet_ngob_reject/docs/ANNOTATION_GUIDELINE.md`.
- Those old thesis label files are **pose format** (5 box fields + 15 keypoint fields per line).
  The importer's `>5 fields` branch is what makes them ingestible — keep that test green.
