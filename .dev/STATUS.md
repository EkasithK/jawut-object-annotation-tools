# Status — 2026-08-03 (end of session 1)

## Now

**Nothing is in progress. The tree is clean, everything is pushed, CI is green.**

All seven phases complete and **v0.1.0 released**, verified by a CI smoke test that launches the
packaged exe on a Windows runner: it starts, serves its frontend, creates a project, creates a
class, and refuses an unauthenticated call.

Release: https://github.com/EkasithK/jawut-object-annotation-tools/releases/tag/v0.1.0
(26 MB Windows zip + the user guide PDF)

### Pick up here next session

Two things are waiting on a human, both on the Windows machine:

1. **Run the released exe by hand.** CI proves it starts; nobody has confirmed it *feels* right
   to label with. Download the zip, extract, double-click, expect the SmartScreen warning
   (More info → Run anyway).
2. **Do the real 1,340-image relabel**, 2 classes → 4, following `docs/HELMET_MIGRATION.md`.
   The dataset is not in any repo — it lives at `C:/Users/kuaut/Desktop/helmet_wit/` per
   `../helmet_ngob_reject/Data/data.yaml`. The migration itself is already covered end to end by
   `tests/integration/test_helmet_migration.py` against a replica containing every awkward case.

Then, in the order I would pick them up, see **Next** below.

### To run it locally right now

```bash
uv run python -m jawut --no-window --port 8000   # then open http://127.0.0.1:8000
```

The server injects the launch token into the page, so a browser works with nothing to paste.
WSL2 forwards localhost, so a Windows browser reaches it. Six real site photos to try it on are
at `../helmet_ngob_reject/Data/paper_material/figure/`.

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

1. **Native folder pickers** via `webview.create_file_dialog(FOLDER_DIALOG)`, replacing the typed
   paths in the Add images, Import labels and Export dialogs. This is the weakest part of the
   experience for a non-technical annotator and the highest-value change left. Needs a small
   endpoint that only works when running windowed, with the typed field as the fallback.
2. **Undo/redo in the UI.** `edit_log` already stores before/after JSON for every save, so the
   data exists; what is missing is an endpoint to walk it and `Ctrl+Z` / `Ctrl+Shift+Z` wired up
   in `Workspace.tsx`.
3. **An icon** at `packaging/icon.ico` — `jawut.spec` picks it up automatically if present, and
   currently ships the default PyInstaller icon.
4. **Class reordering in the UI.** The API (`POST /api/v1/classes/reorder`) and the service are
   done and tested; the palette has no drag handle. Matters because class order decides the
   exported indices.
5. **Bulk reassign in the UI.** `POST /api/v1/annotations/reassign` exists and is tested, but is
   only reachable today through the delete-class dialog.
6. Consider a code-signing certificate if this gets handed to more than a few people — it is the
   only thing standing between them and a SmartScreen warning.

## Open questions / blocked

- None.

## The API, at a glance

Every response is wrapped in `{data, error, meta}`. Everything under `/api/v1` requires the
`X-Jawut-Token` header when `JAWUT_LAUNCH_TOKEN` is set, and returns `409 NO_PROJECT_OPEN` if no
project is open.

| Method | Path | Does |
|---|---|---|
| `GET` | `/api/v1/projects` | Whole welcome state: open project, recents, default location |
| `POST` | `/api/v1/projects` | Create and open |
| `POST` | `/api/v1/projects/open` \| `/close` \| `/forget` | Open, close, drop from recents |
| `GET` | `/api/v1/classes` | List live classes in order |
| `POST` | `/api/v1/classes` | Create |
| `PATCH` | `/api/v1/classes/{id}` | Rename and/or recolour |
| `POST` | `/api/v1/classes/reorder` | Full ordered id list; decides export indices |
| `GET` | `/api/v1/classes/{id}/usage` | Box and image counts, for the delete dialog |
| `POST` | `/api/v1/classes/{id}/delete` | Body carries `reassign_to` or null |
| `POST` | `/api/v1/images/import` | Folder import, copy or link |
| `GET` | `/api/v1/images?status=` | List + status counts |
| `GET` | `/api/v1/images/{id}?status=` | Image, its boxes, and filtered neighbours |
| `GET` | `/api/v1/images/{id}/file` | The image bytes |
| `PATCH` | `/api/v1/images/{id}/status` | Set status |
| `GET`/`PUT` | `/api/v1/annotations/{image_id}` | Read / replace the whole box set |
| `POST` | `/api/v1/annotations/reassign` | Move every box of one class to another |
| `POST` | `/api/v1/labels/preview` | Read a label folder, write nothing |
| `POST` | `/api/v1/labels/import` | Apply with an explicit class mapping |
| `POST` | `/api/v1/export` | Write a YOLO dataset |

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
