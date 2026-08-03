# Status — 2026-08-03

## Now

Phase 1 complete. Ready to start Phase 2 — DB schema, migrations, project create/open.

## Done

- **Planning** — scope, storage model, packaging approach and phases agreed. See `PLAN.md` for the
  spec, `DECISIONS.md` for why each choice was made.
- **Phase 1 — Skeleton**
  - `pyproject.toml` (uv, ruff, mypy strict, pytest), `.pre-commit-config.yaml`, `.gitignore`,
    `.env.example`
  - Sub-project `CLAUDE.md` recording every override of the root standards
  - `README.md` written for the eventual public audience
  - `src/jawut/`: `app.py` (FastAPI factory, lifespan, envelope error handler, launch-token
    dependency, static mount), `models.py` (envelope schemas), `db/connection.py` (per-project
    connection registry, WAL, `probe`/`close_all`)
  - `frontend/`: Vite + React 19 + TS strict, Tailwind v4 with design tokens, typed API client
    with Zod envelope validation, ESLint flat config
  - `.github/workflows/ci.yml` — backend lint/format/typecheck/test, frontend lint/typecheck/build,
    security scan (pip-audit + trivy)
  - 20 tests passing, 100% backend coverage, `ruff` and `mypy --strict` clean, frontend builds

## Next

1. `db/schema.sql` v1 — meta, classes, images, annotations, edit_log
2. `db/migrations.py` — `PRAGMA user_version` runner
3. `config.py` — `%APPDATA%` settings and recent-projects list
4. Projects service + router: create, open, list recent
5. Welcome screen UI (New / Open / Recent)

## Open questions / blocked

- None.

## Notes for the next session

- Toolchain: Python 3.12.3 locally but the venv resolves to 3.11.15; `uv`, node 24.16. Code targets
  py311 (`ruff target-version`, `mypy python_version`) so the Windows CI build stays compatible.
- Dev runs two processes: `uv run uvicorn jawut.app:app --reload --port 8000` and
  `cd frontend && npm run dev` (Vite proxies `/api`, `/health`, `/ready` to :8000). The packaged
  exe instead serves `src/jawut/static/`, which is gitignored because CI produces it.
- `app.py` registers its error handler on **Starlette's** `HTTPException`, not FastAPI's subclass.
  Router-level 404s never pass through the subclass, so registering on the subclass silently skips
  them and breaks the response envelope. Do not "simplify" that import.
- `StaticFiles` is mounted at `/` only when `src/jawut/static/` exists, so tests and a fresh clone
  work without a frontend build. Once SPA routing lands, that mount needs an index.html fallback
  for unknown paths.
- Reference code for Phase 3: the old labeler at
  `../ekasith-phd-thesis/experiments/tools/labeler/` — `static/index.html:262-274` has the
  image↔canvas view transform (`fitView`, `toC`, `toI`, `nToImg`, `imgToN`) worth porting into
  `BoxCanvas.tsx` rather than re-deriving. `app.py:81-90` is the backup-original-once pattern that
  the `edit_log` table replaces.
- Real data for Phase 7: `../helmet_ngob_reject/Data/` (`data.yaml` is 2-class); the 4-class
  taxonomy and labeling rules are in `../helmet_ngob_reject/docs/ANNOTATION_GUIDELINE.md`.
- Those old thesis label files are **pose format** (5 box fields + 15 keypoint fields per line).
  The importer's `>5 fields` branch is what makes them ingestible — keep that test green.
