# Decisions

Append-only. Newest last. One entry per decision: what, why, what was rejected.

---

## 2026-08-03 — SQLite as the working store, YOLO txt as import/export only

**Decision.** Annotations, classes, image records and statuses live in a per-project SQLite
`project.db`. YOLO `.txt` is a format we read and write, never the live store.

**Why.** In YOLO, class identity *is* the integer index, so deleting a class shifts every higher
index and requires rewriting every label file in one atomic pass. A partial failure yields a
dataset that loads and trains fine while being silently wrong. Storing classes under stable UUIDs
and assigning the contiguous integer only at export makes delete/rename/reorder incapable of
corrupting annotations. It also collapses what the old labeler spread across five stores
(`labels/`, `labels_orig/`, `review_state.json`, `qc_flags.json`, `autolabel_conf.json`) into one
transactional file, and makes bulk reassignment a single `UPDATE`.

**Rejected.** Writing txt directly, as the old labeler did. Simpler and directly readable by
training scripts, but unsafe for the class-editing workload this tool exists for. The export
button closes that gap.

---

## 2026-08-03 — Export button only, no live txt mirror

**Decision.** Txt leaves the database only when the user clicks Export.

**Why.** One code path. A live mirror has to react correctly to class rename, class delete, class
reorder and box deletion, each of which can leave stale files behind.

**Rejected.** A "mirror to folder on save" toggle. Reconsider only if the export step proves
annoying in practice.

---

## 2026-08-03 — PyInstaller `onedir` + pywebview, not `onefile` or a browser tab

**Decision.** Ship a zipped folder containing the exe, opening a native pywebview window.

**Why.** `onefile` unpacks to temp on every launch (5–15s vs ~1s) and draws more antivirus false
positives. A native window gives a taskbar icon, a close button that actually ends the process,
and access to OS folder pickers — which matter far more than browser upload when importing 1,340
images.

**Rejected.** `onefile` (single icon, but slow and AV-prone) and opening the default browser
(simplest, but users close the tab and leave the server running).

---

## 2026-08-03 — No auto-labeling in v1

**Decision.** Manual labeling only; no ultralytics or torch dependency.

**Why.** Adding a model takes the bundle from roughly 100 MB to over 2 GB, which undermines the
whole "download and double-click" premise.

**Rejected.** Bundling a helmet detector for pre-annotation. Revisit as an optional separate
download, or as a "point at your own weights" feature, once the core tool is proven.

---

## 2026-08-03 — Stratified 70/15/15 split by default, plus a flat mode

**Decision.** Export offers a seeded split stratified on each image's rarest present class, and a
flat mode that writes one `images/` + `labels/` pair with no split.

**Why.** Stratifying on the rarest present class keeps a rare class like `Helmet_Ngob` from landing
entirely in one split. The flat mode exists because splitting is sometimes better done later by
hand, and mixing splits prematurely is hard to undo.

**Rejected.** Split-only (forces a decision too early) and flat-only (adds a second tool to every
export).

---

## 2026-08-03 — Vite + React + TS, not Next.js

**Decision.** Frontend is Vite + React + TypeScript, built to static files served by FastAPI.

**Why.** Next.js expects a Node server, which cannot be bundled into a Windows exe. Vite emits
plain static assets that PyInstaller can ship. Overrides the root `CLAUDE.md` default.

**Rejected.** Next.js (unbundleable here) and a single vanilla-JS HTML file as in the old labeler
(no build step, but the class manager, import wizard and filters make it unwieldy).

---

## 2026-08-03 — Dev-state files confined to `.dev/`, commit messages clean from day one

**Decision.** All development tracking lives in `.dev/` and is committed. Commit messages are
plain Conventional Commits with no AI attribution, starting from the first commit.

**Why.** Work happens across multiple machines, so state has to travel in the repo. The repo may
go public later; files can be removed in one commit, but commit messages would require a history
rewrite, which is risky and easy to get wrong. So the traces go where cleanup is cheap.

**Rejected.** Keeping tracking files outside the repo (breaks multi-machine work) and cleaning
commit messages later via rebase (risky, and pointless when it can simply be avoided).
