# Jawut Object Annotation Tools

A desktop application for drawing bounding boxes on images and exporting YOLO datasets.

Built for teams that need to relabel or clean up an existing dataset: import images and labels you
already have, fix them, add or remove classes, change the class of boxes that are already drawn,
and export a training-ready dataset. Works on partially labeled sets, where some images have
labels and some do not.

## Features

- **Bounding-box labeling** with zoom, pan, edge-handle resize, and a keyboard-first workflow
- **Import what you already have** — images alone, or images plus YOLO `.txt` labels and a
  `data.yaml`, with a mapping step so your class names land where you intend
- **Resume partial work** — every image tracks whether it is untouched, in progress, finished, or
  flagged for review, and the list can be filtered accordingly
- **Safe class editing** — add, rename, reorder or delete classes at any time, including reassigning
  every box of a class to another class, without corrupting existing annotations
- **YOLO export** — stratified train/val/test split with a fixed seed, or a flat unsplit export,
  with `data.yaml` written for you

## Install

Download the latest zip from [Releases](../../releases), extract it anywhere, and run
`Jawut Object Annotation Tools.exe`. Nothing else is required — no Python, no database, no
installer.

> **Windows SmartScreen** may show "Windows protected your PC" because the application is not code
> signed. Click **More info** then **Run anyway**.

## Documentation

| | |
|---|---|
| **[User Guide](docs/USER_GUIDE.md)** ([PDF](docs/USER_GUIDE.pdf)) | Every step with screenshots, from a blank screen to an exported dataset. Start here. |
| [Migration runbook](docs/HELMET_MIGRATION.md) | Relabeling an existing dataset onto a new set of classes. |

## Getting started

1. Launch the app and choose **New Project**, then pick a name and a folder to keep it in.
2. **Add images** — point at a folder. Images are copied into the project by default, so the
   project folder stays self-contained and can be moved or backed up by copying it.
3. **Add labels** (optional) — point at a folder of YOLO `.txt` files and, if you have one, a
   `data.yaml`. Map each incoming class to a project class, then review the import report.
4. Label. Press `W` to draw a box, a number key to set its class, `D` for the next image.
5. **Export** when done, choosing a split or a flat layout.

### Keyboard

| Key | Action | Key | Action |
|---|---|---|---|
| `W` | new box | `A` / `D` | previous / next image |
| `1`–`9` | set class of the selected box | `Space` | mark done and advance |
| `Ctrl+Z` / `Ctrl+Shift+Z` | undo / redo | `Delete` | delete selected box |
| `F` | fit image to window | `Esc` | cancel drawing / deselect |

## Where your data lives

| What | Where |
|---|---|
| Application settings, recent projects | `%APPDATA%\Jawut\` |
| Projects | The folder you choose, default `Documents\Jawut Projects\<name>\` |

A project folder holds `project.db` — every annotation, class and status — plus an `images/` copy.
Back it up by copying the folder.

## Export format

Standard YOLO detection labels: one `.txt` per image, one line per box,
`<class_index> <cx> <cy> <w> <h>` with all coordinates normalized to `[0,1]`, alongside a
`data.yaml` listing the class names.

An image that has been reviewed and genuinely contains no objects exports an **empty** `.txt` — a
valid background image. Images never opened are excluded by default; a checkbox includes them.

Split exports also write `export_manifest.json` recording the seed, ratios and per-image split
assignment, so the same export can be reproduced later.

## Building from source

Requires Python 3.11+, [uv](https://github.com/astral-sh/uv), and Node 20+.

```bash
uv sync
cd frontend && npm install && npm run build && cd ..

# run in development (two processes)
uv run uvicorn jawut.app:app --reload --port 8000
cd frontend && npm run dev          # proxies /api to :8000

# tests, lint, types
uv run pytest tests/ -v --cov=src --cov-report=term-missing
uv run ruff check . && uv run mypy src/
```

The Windows executable is produced by the release workflow on a Windows runner; PyInstaller cannot
cross-compile, so building it locally requires Windows.
