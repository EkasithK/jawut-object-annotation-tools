-- Schema v1. One database file per project.
--
-- Two rules drive the shape of this schema:
--
--   1. Classes carry stable UUIDs and never a YOLO integer. The contiguous index a
--      class gets in an exported dataset is derived from `order_index` at export
--      time. That is what makes deleting or reordering a class safe: in YOLO the
--      integer *is* the identity, so storing it here would mean rewriting every
--      label file on every class change.
--
--   2. `images.status` distinguishes "never looked at" from "looked at, no objects
--      present". Those export differently — the first is excluded, the second emits
--      an empty .txt as a valid background image — and conflating them is the
--      classic missing-vs-empty .txt dataset bug.

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE classes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    deleted_at  TEXT
) STRICT;

-- Names must be unique among live classes only, so a deleted name can be reused.
CREATE UNIQUE INDEX ix_classes_name_live
    ON classes (name) WHERE deleted_at IS NULL;
CREATE INDEX ix_classes_order
    ON classes (order_index) WHERE deleted_at IS NULL;

CREATE TABLE images (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    -- Relative to the project directory when is_managed = 1, absolute otherwise.
    stored_path TEXT NOT NULL,
    is_managed  INTEGER NOT NULL CHECK (is_managed IN (0, 1)),
    width       INTEGER NOT NULL CHECK (width > 0),
    height      INTEGER NOT NULL CHECK (height > 0),
    sha256      TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (
        status IN ('unlabeled', 'in_progress', 'done', 'needs_review')
    ),
    -- Natural sort key so image10 follows image9 rather than image1.
    sort_key    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
) STRICT;

CREATE UNIQUE INDEX ix_images_sha ON images (sha256);
CREATE INDEX ix_images_status ON images (status);
CREATE INDEX ix_images_sort ON images (sort_key);

CREATE TABLE annotations (
    id         TEXT PRIMARY KEY,
    image_id   TEXT NOT NULL REFERENCES images (id) ON DELETE CASCADE,
    class_id   TEXT NOT NULL REFERENCES classes (id),
    -- Normalized center form, matching YOLO. Pixel coordinates exist only inside
    -- the canvas view transform, never here and never across the API.
    cx         REAL NOT NULL CHECK (cx >= 0.0 AND cx <= 1.0),
    cy         REAL NOT NULL CHECK (cy >= 0.0 AND cy <= 1.0),
    w          REAL NOT NULL CHECK (w > 0.0 AND w <= 1.0),
    h          REAL NOT NULL CHECK (h > 0.0 AND h <= 1.0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX ix_ann_image ON annotations (image_id);
CREATE INDEX ix_ann_class ON annotations (class_id);

-- Append-only history backing undo/redo and "what happened to this image".
CREATE TABLE edit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id   TEXT,
    action     TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE INDEX ix_edit_log_image ON edit_log (image_id, id);
