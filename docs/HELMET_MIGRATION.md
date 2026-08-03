# Migrating the helmet dataset from 2 classes to 4

A runbook for relabeling the ~1,340-image helmet dataset from its current two classes
(`No_Helmet`, `Safety-Helmet`) to the four-class taxonomy in the annotation guideline:
`Helmet`, `Helmet_Ngob`, `Ngob`, `No_Helmet`.

The same sequence is covered end to end by
`tests/integration/test_helmet_migration.py`, against a dataset built to contain every
awkward case the real one has. What follows is the human version.

## Before you start

- The zip from [Releases](../../releases), extracted anywhere.
- The existing dataset, with `images/` and `labels/` folders and its `data.yaml`.
- **A copy of the dataset.** Nothing here modifies your source folders, but a relabel
  is hours of work and a second copy costs nothing.

## 1. Create the project

Run `Jawut Object Annotation Tools.exe`, choose **New Project**, name it something like
`Helmet Relabel`, and accept the default location.

The project is a folder containing `project.db` and an `images/` copy. Back it up by
copying that folder.

## 2. Add the images

**Add images** → point at the dataset's `images/` folder → **Import**.

Leave *Copy into the project* on. The project stays self-contained, so moving or
backing it up is a folder copy, and reorganising your photo folders later cannot break
it.

Check the report: 1,340 imported, 0 skipped. Anything skipped is listed with a reason —
usually a corrupt file, which is worth knowing about before you start labeling.

## 3. Create the four classes

In the class panel on the right, add them **in this order**, because the order decides
the class indices in the exported dataset:

| Order | Class | Hotkey |
|---|---|---|
| 0 | `Helmet` | `1` |
| 1 | `Helmet_Ngob` | `2` |
| 2 | `Ngob` | `3` |
| 3 | `No_Helmet` | `4` |

## 4. Import the existing labels

**Import labels** → point at the dataset's `labels/` folder → **Read folder**.

The `data.yaml` is found automatically, whether it sits beside `labels/` or one level
above. The mapping step then shows the old classes with a box count each. Map them:

| Old class | Maps to | Why |
|---|---|---|
| `No_Helmet` | `No_Helmet` | Unchanged |
| `Safety-Helmet` | `Helmet` | Every hard hat starts as plain `Helmet` |

Nothing becomes `Helmet_Ngob` or `Ngob` at this stage — those are the distinctions the
old two-class labels could not express, and finding them is the work.

Read the import report before continuing. Expect to see:

- **keypoints_dropped** if any labels came from the pose labeler. The box is kept and
  the keypoints discarded, which is correct for a detection dataset.
- **pixels_normalized** where coordinates were in pixels rather than 0–1.
- **malformed** or **out_of_range** for lines that could not be read. Those images are
  marked **Review**, so they are easy to find later.
- **unmatched_label** for `.txt` files with no matching image.

The report can be scrolled and read in full. Nothing is dropped silently.

## 5. Relabel

Filter to **Doing** and work through it. The whole loop is keyboard:

| Key | Action | Key | Action |
|---|---|---|---|
| `W` | draw a box | `A` / `D` | previous / next image |
| `1`–`4` | set the class of the selected box | `Space` | mark done and advance |
| `Ctrl+Z` | undo | `Delete` | delete the selected box |
| `F` | fit to window | `Esc` | cancel / deselect |

For each head, the guideline's two questions decide the class:

|  | **Soft headwear: no** | **Soft headwear: yes** |
|---|---|---|
| **Hard hat: yes** | `Helmet` | `Helmet_Ngob` |
| **Hard hat: no** | `No_Helmet` | `Ngob` |

In practice: select a box, press `2` if there is a woven hat or neck cloth under the
hard hat, `3` if there is soft headwear but no hard hat. Then `Space`.

**An image with no people in it is not a mistake.** Press `Space` with no boxes drawn
and it exports as an empty label — a valid background image. That is different from
never opening it, which excludes the image from the export entirely.

Use the **Review** filter to come back to whatever the importer flagged.

## 6. Retire a class, if you decide to

If you conclude that `No_Helmet` and `Ngob` should not be separate after all, click the
`×` next to `No_Helmet`. The dialog reports exactly how many boxes across how many
images use it, and offers to move them to another class or delete them. Moving them is
one transaction; nothing is left half-changed, and no label file is rewritten.

Reordering or deleting classes is safe at any point. Indices are worked out at export
time, so they cannot go stale.

## 7. Export

**Export** → choose an empty destination folder.

- **Split** with 70 / 15 / 15 and seed 42 gives a training-ready dataset. The split is
  stratified on each image's rarest class, so `Helmet_Ngob` cannot land entirely in
  train and leave its validation numbers meaningless.
- **Flat** gives one `images/` and `labels/` pair if you would rather split by hand.
- Leave *Include images nobody has opened* off. Exporting an untouched image as an
  empty label would assert it has no objects, which nobody has checked.

You get:

```
data.yaml               nc, names, and the split paths
train/images  train/labels
val/images    val/labels
test/images   test/labels
export_manifest.json    seed, ratios, class order, per-image split
```

Keep `export_manifest.json`. It is what lets you reproduce or audit this exact split
later.

## 8. Check before training

- `data.yaml` lists `nc: 4` and the names in the order you created them.
- Every image has a matching `.txt`; a few are empty, and those are your backgrounds.
- The class counts in `export_manifest.json` look like what you expect. A class with
  almost nothing in it usually means a mapping mistake in step 4.

Then train against `data.yaml` as usual.

## If something looks wrong

**Class counts are not what you expected.** Check the mapping you chose in step 4. You
can re-import the labels with *Replace boxes* on to start that part over.

**An image will not open.** If it was imported with *Copy into the project* off and the
original moved, the file cannot be found. Re-import it.

**The export refuses to run.** The destination has to be empty. Exporting into a folder
that already has a dataset in it would half-overwrite it, and the damage would only
surface at training time.
