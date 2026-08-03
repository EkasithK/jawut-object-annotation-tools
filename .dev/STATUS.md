# Status — 2026-08-03 (end of session 2)

## Now

**Nothing is in progress. The tree is clean, everything is pushed.**

Session 2 shipped **v0.2.0**: native folder pickers everywhere, a one-step "Open existing dataset"
flow, and the warm light theme.

### Pick up here next session

Three things are waiting on a human, all on the Windows machine:

1. **Verify the native dialogs on Windows.** This is the one thing that could not be tested here.
   `desktop.pick_folder` calls `webview.create_file_dialog` from an `anyio` worker thread; the
   WinForms/EdgeChromium backend marshals to the UI thread internally, so it should be fine, but
   nothing on Linux exercises it. If a dialog hangs or the window locks up, the fix is to marshal
   explicitly through the pywebview window rather than calling from a worker thread. The typed
   path field stays as a fallback either way, so a failure here degrades rather than blocks.
2. **Run the released exe by hand** and confirm the new theme and the wizard feel right to label with.
3. **Do the real 1,340-image relabel**, 2 classes to 4, following `docs/HELMET_MIGRATION.md`. The
   dataset lives at `C:/Users/kuaut/Desktop/helmet_wit/` per `../helmet_ngob_reject/Data/data.yaml`.
   With v0.2.0 the first half of that runbook collapses into **Open existing dataset** — browse to
   the folder, confirm, done. The runbook has not been rewritten around that yet.

### To run it locally right now

```bash
uv run python -m jawut --no-window --port 8000   # then open http://127.0.0.1:8000
```

The server injects the launch token into the page, so a browser works with nothing to paste.
WSL2 forwards localhost, so a Windows browser reaches it. **Browse buttons will not appear** —
`native_dialogs` is false without a desktop window, by design. Six real site photos to try it on
are at `../helmet_ngob_reject/Data/paper_material/figure/`.

## Done

### Session 1 — v0.1.0

- **Phase 1 — Skeleton.** uv/ruff/mypy-strict/pytest, pre-commit, CI (lint, format, typecheck,
  test, pip-audit + trivy), private repo under `EkasithK`.
- **Phase 2 — Core.** Schema v1 with `STRICT` tables and CHECK constraints, `user_version`
  migrations, `%APPDATA%` settings with atomic writes, project create/open, welcome screen.
- **Phase 3 — Labeling.** Image import (copy or link, sha256 dedupe, per-file skip reasons),
  `BoxCanvas` with zoom/pan/draw/resize, class CRUD with safe delete, status filters, full
  keybindings.
- **Phase 4 — Label import.** Two-step preview then apply with an explicit class mapping.
  Auto-fixes only the unambiguous; quarantines everything else with file and line.
- **Phase 5 — Export.** Stratified split (seeded) and flat mode, `data.yaml` in Ultralytics shape,
  `export_manifest.json` for reproducibility.
- **Phase 6 — Packaging.** Loopback port + per-launch token, pywebview window owning the process,
  PyInstaller `onedir` spec, Windows release workflow with a smoke test.
- **Phase 7 — Migration.** `tests/integration/test_helmet_migration.py` runs the whole 2-to-4 class
  job against a replica; `docs/HELMET_MIGRATION.md` is the runbook.

### Session 2 — v0.2.0

- **Native folder pickers.** `jawut/desktop.py` holds the window handle `__main__` registers;
  `/api/v1/system/capabilities` and `/api/v1/system/browse` expose it. `PathField.tsx` renders
  **Browse…** only when capabilities says yes, and keeps the typed input as the fallback. Wired
  into all five path fields: new project location, add images, import labels, export destination,
  and the new open-project field.
- **Open a project that is not in Recent.** There was previously no route to one at all — a fresh
  machine or a cleared list was a dead end.
- **"Open existing dataset" wizard.** `services/dataset.py` + `routers/datasets.py`. `scan` reports
  layout, counts and class names without writing; `adopt` creates the project and imports images,
  classes and labels in one call. Detects `images`/`labels` pairs, Ultralytics splits and flat
  folders. Classes are created in `data.yaml` order so every `.txt` index keeps its meaning, and
  every label folder is read before any class is created so a class used only in `test/` still
  gets one.
- **Explicit `data.yaml` picker in Import labels.** `importer.preview` takes an optional path.
  Auto-discovery only ever looked beside the labels folder and one level up, which is why classes
  showed up as `class_0, class_1, …` for a dataset whose config sits at the top of the tree.
- **Warm light theme.** Cream surfaces, antique gold accent, dark canvas well behind its own
  `--color-canvas*` tokens. `--color-on-accent` added because filled buttons used `text-surface-0`,
  which became cream-on-gold once the surfaces flipped.
- **Docs.** All 17 guide screenshots regenerated in the new theme, two of them new
  (`01a-open-dataset`, `01b-dataset-found`), the guide rewritten around the new routes, PDF
  rebuilt in the new palette. The release workflow now attaches `docs/USER_GUIDE.pdf` itself
  rather than relying on a manual upload. Removed a `Ctrl+Z` / `Ctrl+Shift+Z` row from the README
  keyboard table — it documented an undo feature that does not exist.
- 326 tests passing, 94% backend coverage, `ruff` and `mypy --strict` clean, frontend builds,
  eslint clean.

## Next

Nothing is blocking. In rough order of value:

1. **Undo/redo.** `edit_log` already stores before/after JSON for every save, so the data exists;
   what is missing is an endpoint to walk it and `Ctrl+Z` / `Ctrl+Shift+Z` in `Workspace.tsx`.
   Note `Workspace.tsx:221` returns early on any modifier key, so that guard has to be narrowed
   first. The README no longer claims this works.
2. **An icon** at `packaging/icon.ico` — `jawut.spec` picks it up automatically if present, and
   currently ships the default PyInstaller icon. More noticeable now the app looks deliberate.
3. **Class reordering in the UI.** `POST /api/v1/classes/reorder` and the service are done and
   tested; the palette has no drag handle. Matters because class order decides exported indices.
4. **Bulk reassign in the UI.** `POST /api/v1/annotations/reassign` exists and is tested, but is
   only reachable through the delete-class dialog.
5. **Rewrite `docs/HELMET_MIGRATION.md` around the wizard** — its first half is now one click.
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
| `GET` | `/api/v1/system/capabilities` | Whether native dialogs exist (false outside the window) |
| `POST` | `/api/v1/system/browse` | Open a folder or data.yaml chooser; `path: null` on cancel |
| `POST` | `/api/v1/datasets/scan` | Read a dataset folder, write nothing |
| `POST` | `/api/v1/datasets/adopt` | Create a project from it, images + classes + labels |

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
- **Native dialogs need the desktop window.** `desktop.set_window` is called by `__main__`
  only in windowed mode, so `capabilities` reports false under `uvicorn`, `--no-window` and
  every test. That is deliberate — the frontend hides **Browse…** and leaves the typed field.
  Do not "fix" a missing Browse button in dev; check you are running the real window.
- The dialog blocks until the user answers, so `routers/system.py` runs it through
  `anyio.to_thread.run_sync`. On the event loop it would stall every other request for as
  long as the chooser stayed open.
- Regenerating the screenshots needs a server **without** a launch token — use
  `uv run uvicorn jawut.app:app --port <port>`, not `python -m jawut`, because the capture
  script drives the API directly with no `X-Jawut-Token` header. It also needs
  `PLAYWRIGHT_BROWSERS_PATH` pointed at the real `~/.cache/ms-playwright`, since `HOME` is
  redirected to a throwaway directory to keep local paths out of the images. The script fakes
  `capabilities` and `browse` with `page.route` so the Browse buttons appear in the captures —
  without that the guide would show a UI nobody running the exe ever sees.
- Guide screenshots 05 onward are converted to JPEG after capture; 01-04 stay PNG. The
  photographs triple the PDF size as PNG for no visible gain, and the flat UI shots stay
  sharper as PNG.
- Screenshots for the guide are regenerated by `.dev/capture_screenshots.py`. It drives the app
  with Playwright, seeds boxes through the API rather than simulating drags (a precise drag is far
  more fragile), and runs with `HOME` and `JAWUT_APP_DATA_DIR` pointed at a throwaway directory so
  no local paths appear in the images. Needs a browser once:
  `uv run --with playwright python -m playwright install chromium`.
- PyInstaller can be run locally on Linux to validate the spec end to end. It produces a Linux
  binary, but it proves the bundle, the hidden imports and the data files are right — which is how
  the `schema.sql` bug was found before release.
