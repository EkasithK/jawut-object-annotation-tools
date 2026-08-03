# Jawut Object Annotation Tools — Plan

Durable spec. Edit only when scope genuinely changes, and log the reason in `DECISIONS.md`.

## Goal

A standalone Windows desktop app for **bounding-box object detection labeling only** (no
keypoints), runnable by double-clicking with nothing to install. It must import partially
labeled datasets that carry foreign class names, allow adding/deleting/renaming classes and
reassigning existing boxes without corrupting data, and export YOLO txt for training.

Driving use case: relabel the ~1,340-image helmet dataset from 2 classes
(`No_Helmet`, `Safety-Helmet`) to the 4-class taxonomy `Helmet`, `Helmet_Ngob`, `Ngob`,
`No_Helmet`, replacing the Roboflow dependency.

**Out of scope for v1:** auto-labeling or any ML dependency (would take the app from ~100 MB to
2+ GB), multi-user/hosted deployment, merge or collaboration features, macOS.

## Decisions

| Decision | Choice | Reason |
|---|---|---|
| Platform | Windows only | Only target for now |
| Distribution | PyInstaller `onedir` in a zip + `pywebview` window | ~1s start vs 5–15s; fewer AV false positives than `onefile` |
| Store | SQLite `project.db`; YOLO txt is import/export only | Safe class delete/reassign, one consistent state, `sqlite3` is stdlib so adds 0 bytes |
| Export | Explicit button, no live mirror | One code path, no edge cases on class rename/delete |
| Splits | Stratified by class, 70/15/15 default, plus flat no-split mode | Flat mode keeps images/labels unmixed for manual splitting |
| Frontend | Vite + React + TypeScript | Real UI surface: class manager, import wizard, filters |
| Auto-label | Excluded | Keeps the exe small; manual labeling only |

### Why SQLite instead of writing txt directly

In YOLO, class identity *is* the integer index. Deleting class 1 of 4 shifts every higher index
down, so all label files would need rewriting in one atomic pass — and a partial failure produces
a dataset that loads and trains fine while being silently wrong.

Classes therefore carry **stable UUIDs**, and the contiguous YOLO integer is computed only at
export time from `order_index`. Deleting, renaming or reordering a class is a metadata change that
cannot corrupt annotations, and "reassign every `No_Helmet` to `Ngob`" is one `UPDATE` rather than
1,340 file rewrites.

## Layout

```
src/jawut/
  __main__.py          entry: uvicorn + pywebview window
  app.py               FastAPI factory, lifespan
  config.py            %APPDATA% paths, recent projects
  db/                  schema.sql, connection.py (WAL), migrations.py (user_version)
  models.py            Pydantic v2 schemas
  services/            projects, images, classes, annotations, importer, exporter
  routers/             projects, images, classes, annotations, io
  static/              built frontend (gitignored)
frontend/src/
  canvas/BoxCanvas.tsx        zoom/pan/draw/resize
  panels/{ImageList,ClassManager,BoxList}.tsx
  import/ImportWizard.tsx
  export/ExportDialog.tsx
  api/client.ts               typed fetch + Zod
  store.ts                    Zustand
tests/{unit,integration}
packaging/jawut.spec
```

## Data model

One `project.db` per project. Full DDL lives in `src/jawut/db/schema.sql`.

- `meta` — key/value: project name, created_at, app_version
- `classes` — uuid PK, name, color, `order_index` (drives YOLO index at export), soft `deleted_at`
- `images` — uuid PK, filename, `stored_path`, `is_managed` (copied vs linked), width, height,
  sha256 (dedupe), `status`, sort_key
- `annotations` — uuid PK, image_id, class_id, normalized `cx cy w h`
- `edit_log` — append-only action log backing undo/history

**`status` is what makes partial work resumable.** `unlabeled` means untouched; `done` with zero
annotations means "looked, there are genuinely no objects" — a true background image. Collapsing
those two is the classic YOLO missing-`.txt` vs empty-`.txt` bug. The distinction drives both the
image filter and what export writes.

## Behaviour of the tricky operations

- **Class delete** — count usage first, show "`Ngob` is used by 412 boxes across 89 images", offer
  *reassign to another class* or *delete those boxes*. One transaction, then soft-delete the class.
  Other classes' `order_index` untouched; nothing on disk rewritten.
- **Class rename / reorder** — pure metadata. Reordering only changes the export integer.
- **Change a box's class** — one field update, from the palette or number keys.

## Import

1. Images: pick a folder, read dimensions with Pillow, sha256 for dedupe, copy into
   `<project>/images/` by default; *Advanced* checkbox links in place for very large sets.
2. Labels (optional): pick a folder, match to images by filename stem.
3. Class source: `data.yaml` `names:` if present, else scan txt for the highest index and generate
   `class_0…class_n` placeholders.
4. **Class mapping step** — each incoming class maps to an existing project class, *create new*, or
   *ignore*. This is what stops someone's class 0 `head` silently becoming `Helmet`.
5. Per-line validation with auto-fix only where unambiguous:
   - `>5` fields → pose-format line (the thesis data is exactly this): keep the box, drop
     keypoints, note it in the report
   - any coordinate `> 1.5` → pixel coordinates, normalize by image dimensions
   - non-positive `w`/`h`, or coords implying `x1y1x2y2` → quarantine, never guess
   - class index outside the mapping → quarantine
   - marginal overflow such as `1.0001` → clamp silently
6. Import report: counts plus every issue with file and line, saveable to txt. Nothing is silently
   dropped.

Labeled images become `in_progress`; images with no label file stay `unlabeled`; an existing empty
`.txt` imports as `done` with zero boxes.

## Export

Dialog takes a destination, a split mode, and *include unlabeled images* (default off — exporting
untouched images as empty labels would teach the model they are backgrounds).

- **Split** (default): 70/15/15, seed 42, stratified by each image's rarest present class so rare
  classes like `Helmet_Ngob` cannot land entirely in one split.
- **Flat**: single `images/` + `labels/`, no split, for manual splitting later.

Writes `data.yaml` in the same shape as the existing helmet dataset (`train`/`val`/`test`, `nc`,
`names` as a list) plus `export_manifest.json` recording seed, ratios, class order and per-image
split assignment, so an export is reproducible. Images `done` with zero boxes emit an empty `.txt`.

## Desktop packaging

- Uvicorn on `127.0.0.1` port 0 (OS-assigned), with a random per-launch token the frontend must
  send, so no other local process can reach the API.
- `pywebview` EdgeChromium window (WebView2 ships with Win10/11); closing it triggers the FastAPI
  lifespan shutdown and exits.
- Native OS folder pickers — far better than browser upload for 1,340 images.
- `--windowed`, with icon. Nothing written next to the exe: settings in `%APPDATA%\Jawut\`,
  project data in the user-chosen folder.
- Unsigned for v1; the README documents the SmartScreen "More info → Run anyway" step.

## UI direction

Three zones, keyboard-first, dark and low-chrome — CVAT's speed without its clutter. Left image
strip with status dots and a filter (All / Unlabeled / In progress / Done / Review), centre canvas
taking all remaining space, right panel with class palette and this image's box list. One accent
colour plus per-class colours, generous spacing, crisp 1px borders, no gradients.

Keybindings are a v1 requirement, not polish — they are the entire reason CVAT feels fast:

| Key | Action | Key | Action |
|---|---|---|---|
| `W` | new box | `A` / `D` | prev / next image |
| `1`–`9` | set class | `Space` | mark done + next |
| `Ctrl+Z` / `Ctrl+Shift+Z` | undo / redo | `Delete` | delete selected box |
| `F` | fit to window | `Esc` | cancel / deselect |

---

## Phases

### Phase 1 — Skeleton ✅
- [x] `pyproject.toml`, ruff + mypy strict + pytest config
- [x] `.pre-commit-config.yaml`, `.gitignore`, `.env.example`
- [x] `.dev/` tracking files seeded
- [x] Sub-project `CLAUDE.md` recording overrides of the root standards
- [x] `README.md`
- [x] Python package skeleton under `src/jawut/`
- [x] Vite + React + TS frontend scaffold
- [x] `.github/workflows/ci.yml` — lint, format, typecheck, test, security scan
- [x] Private repo created under `EkasithK`, first commit pushed

### Phase 2 — Core ✅
- [x] `db/schema.sql` v1
- [x] `db/connection.py` — WAL, `foreign_keys=ON`, per-project connection
- [x] `db/migrations.py` — `PRAGMA user_version` runner
- [x] `config.py` — `%APPDATA%` settings, recent projects list
- [x] `app.py` — FastAPI factory + lifespan
- [x] `session.py` — the one open project, shared by every router
- [x] Projects service + router: create, open, close, forget, list recent
- [x] Welcome screen UI (New / Recent)

### Phase 3 — Labeling ✅
- [x] Image import: copy into project or link, Pillow dimensions, sha256 dedupe
- [x] `BoxCanvas`: fit / zoom / pan
- [x] Draw and resize boxes with edge handles
- [x] Class CRUD; delete dialog with usage count and reassign-or-delete
- [x] Box class reassignment
- [x] Status filter bar
- [x] Full keybindings
- [x] Undo / redo backed by `edit_log`

### Phase 4 — Label import ✅
- [x] `data.yaml` parsing and class inference
- [x] Per-line validation and quarantine rules
- [x] Class-mapping wizard UI
- [x] Import report, saveable to txt

### Phase 5 — Export ✅
- [x] Stratified split by rarest present class, seeded
- [x] Flat no-split mode
- [x] `data.yaml` + `export_manifest.json`
- [x] Empty `.txt` for `done` images with zero boxes
- [x] Export dialog UI

### Phase 6 — Packaging ✅
- [x] `__main__.py`: uvicorn on port 0 + launch token + pywebview window
- [x] Native folder pickers
- [x] Clean shutdown on window close
- [x] `packaging/jawut.spec` (onedir, windowed, icon)
- [x] `.github/workflows/release.yml` on `windows-latest`
- [x] First end-to-end exe verified on a clean Windows machine

### Phase 7 — Real run ✅
- [x] Import the real helmet images + 2-class labels
- [x] Map to the 4-class taxonomy, add `Helmet_Ngob` and `Ngob`
- [x] Reassign a batch, delete a class with reassignment
- [x] Export split, verify `data.yaml` and spot-check `.txt` against the UI
- [x] Confirm empty-vs-missing `.txt` survives an import → export round trip

## Verification

- `pytest tests/ -v --cov=src --cov-fail-under=80` and `mypy src/` clean
- Round-trip on the real helmet dataset as described in Phase 7
- Download the CI-built zip on a clean Windows machine and complete new-project → import → label →
  export without ever opening a terminal
