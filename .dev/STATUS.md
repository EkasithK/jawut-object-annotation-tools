# Status — 2026-08-03

## Now

All seven phases complete, **v0.1.0 released**, and the Windows build verified by CI's smoke
test — the packaged exe launches, serves its frontend, creates a project and enforces its launch
token on a real Windows machine.

Release: https://github.com/EkasithK/jawut-object-annotation-tools/releases/tag/v0.1.0
(26 MB zip + the user guide PDF)

The one thing not yet done is the **real run on the actual 1,340 helmet images**, which cannot
happen on this machine — the dataset lives on the Windows box (`C:/Users/kuaut/Desktop/helmet_wit/`
per `../helmet_ngob_reject/Data/data.yaml`). The migration is encoded as an automated test against
a faithful replica, and `docs/HELMET_MIGRATION.md` is the runbook for doing it for real.

## Done

- **Phase 1 — Skeleton.** uv/ruff/mypy-strict/pytest, pre-commit, CI (lint, format, typecheck,
  test, pip-audit + trivy), private repo under `EkasithK`.
- **Phase 2 — Core.** Schema v1 with `STRICT` tables and CHECK constraints, `user_version`
  migrations, `%APPDATA%` settings with atomic writes, project create/open, welcome screen.
- **Phase 3 — Labeling.** Image import (copy or link, sha256 dedupe, per-file skip reasons),
  `BoxCanvas` with zoom/pan/draw/resize, class CRUD with safe delete, status filters, full
  keybindings.
- **Phase 4 — Label import.** Two-step preview then apply with an explicit class mapping.
  Auto-fixes only the unambiguous (pixel coordinates, rounding overflow); quarantines everything
  else with file and line. Pose-format lines keep the box and drop keypoints.
- **Phase 5 — Export.** Stratified split (seeded, on each image's rarest class) and flat mode,
  `data.yaml` in Ultralytics shape, `export_manifest.json` for reproducibility.
- **Phase 6 — Packaging.** `__main__.py` on an OS-assigned loopback port with a per-launch token,
  pywebview window owning the process, PyInstaller `onedir` spec, Windows release workflow.
- **Phase 7 — Migration.** `tests/integration/test_helmet_migration.py` runs the whole 2→4 class
  job against a replica containing every awkward case; `docs/HELMET_MIGRATION.md` is the runbook.
- **Docs.** `docs/USER_GUIDE.md` with 15 screenshots from a real session, and `docs/build_pdf.py`
  to render it; the PDF is attached to the release for handing to someone who will never open the
  repository.
- 281 tests passing, 94% backend coverage, `ruff` and `mypy --strict` clean, frontend builds.

## Next

Nothing is blocking. In rough order of value:

1. **Run the real migration** on the Windows machine, following `docs/HELMET_MIGRATION.md`.
   That is the only remaining unknown.
2. Try the released zip on a Windows machine that has never had Python installed. CI proves it
   runs; a human still has to confirm it *feels* right.
3. Undo/redo in the UI. The `edit_log` table already records before/after for every save, so the
   data is there; only the UI and an endpoint are missing.
4. An icon (`packaging/icon.ico`) — the spec picks it up automatically if present.
5. Native folder pickers via pywebview, replacing the typed paths in the import and export dialogs.
   Typed paths work but are the weakest part of the experience for a non-technical user.

## Open questions / blocked

- None.

## Notes for the next session

- Toolchain: `uv` venv on Python 3.11.15, node 24.16. Code targets py311 so the Windows CI build
  stays compatible.
- Dev runs two processes: `uv run uvicorn jawut.app:app --reload --port 8000` and
  `cd frontend && npm run dev`. Or run the real entry point with
  `uv run python -m jawut --no-window --port 8000`, which prints the launch token —
  API calls then need `X-Jawut-Token`.
- Set `JAWUT_APP_DATA_DIR` to a scratch path when testing so real settings are untouched.
- **Any non-Python file the app reads at runtime needs two things**: resolution through
  `jawut.resources.package_file`, and an entry in `datas` in `packaging/jawut.spec`. Missing
  either produces a build that works from source and fails only once packaged. This already bit
  once — `schema.sql` was absent from the bundle, so every packaged project creation failed while
  everything passed locally. The release smoke test now creates a project and a class for exactly
  this reason.
- The launch token is injected into `index.html` **by the server**, not by `evaluate_js` after the
  window opens. The latter races the app's first request.
- `app.py` registers its error handler on **Starlette's** `HTTPException`, not FastAPI's subclass;
  router-level 404s never pass through the subclass.
- `StaticFiles` is mounted at `/` after an explicit `/` route, so the token-injecting index wins.
  Client-side routing would need an index.html fallback for unknown paths.
- CI gotchas already hit: `aquasecurity/trivy-action` tags are `v`-prefixed, and `pip-audit`
  cannot audit the environment because `jawut` is unpublished — the workflow audits
  `uv export --no-emit-project` output instead.
- Test images must differ by more than a little: JPEG quantization collapses near-identical solid
  colours into byte-identical files, which the importer correctly treats as duplicates. The
  `make_image` fixture spaces the channels widely for this reason.
- **A windowed Windows build has no console: `sys.stdout` and `sys.stderr` are `None`.** The first
  `print`, and uvicorn's logging setup, then raise and kill the process. `ensure_streams()` in
  `__main__.py` handles it. Nothing outside Windows reproduces this, and it took a failed release
  build to surface — do not remove that call.
- Screenshots for the guide are regenerated by `.dev/capture_screenshots.py`. It drives the app
  with Playwright, seeds boxes through the API rather than simulating drags (a precise drag is far
  more fragile), and runs with `HOME` and `JAWUT_APP_DATA_DIR` pointed at a throwaway directory so
  no local paths appear in the images. Needs a browser once:
  `uv run --with playwright python -m playwright install chromium`.
- PyInstaller can be run locally on Linux to validate the spec end to end. It produces a Linux
  binary, but it proves the bundle, the hidden imports and the data files are right — which is how
  the `schema.sql` bug was found before release.
