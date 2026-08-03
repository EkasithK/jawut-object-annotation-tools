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

---

## 2026-08-03 — Whole-image annotation saves rather than per-box endpoints

**Decision.** The client sends the complete set of boxes for one image and the server replaces
them, instead of exposing create/update/delete per box.

**Why.** It frees the client to batch edits without an id-reconciliation protocol, and makes every
save one atomic transaction, so a rejected edit cannot leave an image half-updated. Images carry a
handful of boxes, so the payload is trivial.

**Rejected.** Per-box REST endpoints. More conventional, but they turn a drag that moves and
resizes several boxes into a sequence of calls that can partially fail.

---

## 2026-08-03 — The launch token is injected server-side into index.html

**Decision.** The server rewrites `index.html` to include the per-launch token, rather than the
desktop shell calling `evaluate_js` after the window opens.

**Why.** `evaluate_js` races the page: React can issue its first request before the injection
lands, and that request is rejected. Injecting server-side is deterministic.

**Rejected.** `webview.evaluate_js` on window load (racy), and baking a token into the built assets
(it would then be identical for every launch and every user, which defeats the point).

---

## 2026-08-03 — Runtime data files go through `jawut.resources.package_file`

**Decision.** Every non-Python file read at runtime is resolved through one helper, and listed in
`datas` in the PyInstaller spec.

**Why.** Only `.py` files go inside a PyInstaller archive; everything else is unpacked to
`sys._MEIPASS`. Building the bundle locally revealed `schema.sql` was never bundled, so every
packaged project creation failed while the source tree worked perfectly. A single helper makes the
requirement visible in one place, and the release smoke test now creates a project so the same
class of bug cannot reach a user.

**Rejected.** Inlining the schema as a Python string (loses SQL syntax highlighting and diffs), and
resolving paths ad hoc at each call site (exactly what caused the bug).

---

## 2026-08-03 — Splits are stratified on each image's rarest present class

**Decision.** Export groups images by the rarest class they contain, then splits within each group.

**Why.** A detection image carries several classes at once, so there is no single label to
stratify on. Keying on the rarest present class stops a scarce class — `Helmet_Ngob` is the whole
reason this dataset is being relabeled — from landing entirely in one split, which would make its
validation numbers meaningless.

**Rejected.** Plain random splitting (can strand a rare class), and multi-label stratification
(materially more complex for a gain that does not show up at this dataset size).

---

## 2026-08-03 — Native dialogs live behind an API, with the typed field as fallback

**Decision.** `jawut.desktop` holds the pywebview window handle that `__main__` registers, and
`/api/v1/system/{capabilities,browse}` exposes it. The frontend asks `capabilities` once and only
renders **Browse…** when the answer is yes; the path input stays editable either way.

**Why.** Typing a Windows path was the single worst part of the experience for a non-technical
annotator, and it appeared in five places. A native dialog only exists inside the desktop window,
so the dev server in a browser, the `--no-window` build and every test have no way to open one —
if the button were the only route, those would all be dead ends. The dialog blocks until answered,
so the route runs it on a worker thread via `anyio.to_thread`; on the event loop it would stall
every other request for as long as the chooser stayed open.

**Rejected.** A `<input type="file" webkitdirectory>` (gives file handles, not the folder path the
server needs, and cannot pick an empty output folder), and calling pywebview's JS bridge directly
from the page (splits path handling across two runtimes for no gain).

---

## 2026-08-03 — "Open existing dataset" reads the folder before creating anything

**Decision.** `datasets/scan` reports layout, counts and class names and writes nothing;
`datasets/adopt` then creates the project, imports the images, creates the classes in `data.yaml`
order and applies the labels under an identity mapping.

**Why.** The three-step route asked someone to understand the shape of their own data before the
tool would help them, and most people arrive with a folder a training script wrote. Reading first
means a wrong guess is not a dead end — an unlabeled folder reports "no labels yet" and the same
button still works. Classes are created in config order so the integer in every `.txt` keeps its
meaning, which is the one thing a relabel cannot get wrong. `adopt` reads every label folder before
creating any class, because a class used only in `test/` would otherwise have nowhere to land.

**Rejected.** Auto-detecting on the welcome screen without a confirmation step (silently building
the wrong project from a folder full of unrelated images), and reusing the existing three endpoints
from the frontend (four round trips, and a half-built project if one fails).

---

## 2026-08-03 — Light chrome, dark canvas

**Decision.** The palette is warm cream with an antique-gold accent; the canvas well stays dark
via its own `--color-canvas*` tokens.

**Why.** Requested. The split is not a compromise — photographs and the class colours drawn over
them read best against something dark, and inverting the canvas too would mean darkening every
class colour to keep it visible. Accent and status values were picked to clear 4.5:1 as text on
cream, and `--color-on-accent` exists because the old buttons used `text-surface-0`, which became
cream-on-gold when the surfaces flipped.

**Rejected.** A light/dark toggle (doubles the surface area to check on every screen for a
single-user desktop tool), and a light canvas (washes out bright box colours).

---

## 2026-08-03 — Every box is drawn twice, and the palette avoids the outdoors

**Decision.** A dark halo stroke goes under every coloured box stroke and label chip, and the
default class palette is saturated colours that do not occur in dirt, vegetation or machinery.

**Why.** A single coloured line is invisible wherever the scene behind it is a similar colour.
On construction photographs that is most of the frame, and the old palette made it certain —
sand, olive, umber and a muted green are exactly what a site is made of. The complaint arrived
from the excavator labeling work before this project existed. The halo is the part that actually
fixes it: it gives a box a dark edge against sky and a bright edge against mud, so visibility
stops depending on the background and therefore on the palette. The palette change is the second
line of defence, and only affects new classes — projects keep colours already saved.

**Rejected.** Picking a "safer" palette alone (whatever is chosen, some scene defeats it), and
scaling stroke width with zoom (constant screen-space weight is what every comparable tool does,
and a stroke that thickens as you zoom in hides the boundary you zoomed in to see).

---

## 2026-08-03 — The SmartScreen warning is documented as a first-class topic

**Decision.** The README, the user guide and the release body each carry a full explanation of
the Windows SmartScreen warning: the exact clicks, the reason, what can be verified, and the
Unblock fallback.

**Why.** It is the first thing a new user meets, and it reads as "this file is dangerous" when it
actually means "Windows does not recognise the publisher". Without the explanation a
non-technical annotator either refuses to run the tool or runs it uneasily. Repeating it in three
places is deliberate — people arrive at each of those surfaces independently, and the one who
lands on the release page never sees the README.

**Rejected.** A single link to one canonical explanation (the person who needs it most is the
least likely to follow a link), and buying a code-signing certificate for now — it is the real
fix, but it is a recurring cost that only makes sense once the audience is larger than a few
people.

---

## 2026-08-03 — The bundle unblocks itself, via PowerShell

**Decision.** Every frozen launch runs `Unblock-File` over its own directory before importing
pywebview, and if the window still fails a user32 message box explains why and offers the browser.

**Why.** The first person to double-click a release got a stack trace and no application.
Explorer's *Extract All* had copied the internet mark onto all 287 files, and .NET Framework will
not load `Python.Runtime.dll` from an internet-zone file — so pywebview died before anything
reached the screen, in a build with no console to report it. Nothing about that failure suggests
"a file property is wrong" to the person seeing it.

Doing it in-process was tried first and shipped broken as v0.3.1: deleting an alternate data
stream by path fails on Windows with "the filename, directory name, or volume label syntax is
incorrect", from `os.remove` and from `cmd`'s `del` equally, and the loop swallowed that as an
ordinary `OSError`. `Unblock-File` is what Windows documents, and it was confirmed working on the
same files. It runs unconditionally rather than only when a mark is found, because detecting one
means reading the stream that cannot reliably be addressed in the first place.

**Rejected.** Telling users to unblock the zip themselves and nothing more (the README says it,
but the failure mode gives them no reason to connect the two); a code-signing certificate, which
is the real fix for this and for SmartScreen but is a recurring cost that only makes sense with a
larger audience; and retrying the window after unblocking, since a half-initialised pythonnet is
not reliably recoverable in the same process.
