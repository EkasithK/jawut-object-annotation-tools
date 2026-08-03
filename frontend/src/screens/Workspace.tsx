import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import {
  createClass,
  deleteClass,
  getImage,
  imageFileUrl,
  listClasses,
  listImages,
  saveBoxes,
  updateClass,
  type DraftBox,
  type ImageDetail,
  type ImageRecord,
  type ImageStatus,
  type ObjectClass,
  type StatusCounts,
} from "../api/labeling";
import { closeProject } from "../api/projects";
import { BoxCanvas } from "../canvas/BoxCanvas";
import { DeleteClassDialog } from "../components/DeleteClassDialog";
import { ExportDialog } from "../components/ExportDialog";
import { ImportImagesDialog } from "../components/ImportImagesDialog";
import { ImportLabelsDialog } from "../components/ImportLabelsDialog";
import { BoxList } from "../panels/BoxList";
import { ClassPalette } from "../panels/ClassPalette";
import { ImageList } from "../panels/ImageList";
import { useAppStore } from "../store";

const EMPTY_COUNTS: StatusCounts = {
  unlabeled: 0,
  in_progress: 0,
  done: 0,
  needs_review: 0,
  total: 0,
};

export function Workspace() {
  const project = useAppStore((s) => s.project);
  const setProject = useAppStore((s) => s.setProject);

  const [classes, setClasses] = useState<ObjectClass[]>([]);
  const [images, setImages] = useState<ImageRecord[]>([]);
  const [counts, setCounts] = useState<StatusCounts>(EMPTY_COUNTS);
  const [filter, setFilter] = useState<ImageStatus | "all">("all");

  const [detail, setDetail] = useState<ImageDetail | null>(null);
  const [boxes, setBoxes] = useState<DraftBox[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [activeClassId, setActiveClassId] = useState<string | null>(null);
  const [drawMode, setDrawMode] = useState(false);
  const [fitToken, setFitToken] = useState(0);

  const [importOpen, setImportOpen] = useState(false);
  const [labelsOpen, setLabelsOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ObjectClass | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const describe = (e: unknown) =>
    e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);

  const refreshImages = useCallback(async () => {
    const listed = await listImages(filter === "all" ? undefined : filter);
    setImages(listed.images);
    setCounts(listed.counts);
    return listed.images;
  }, [filter]);

  const refreshClasses = useCallback(async () => {
    const listed = await listClasses();
    setClasses(listed.classes);
    setActiveClassId((current) =>
      current && listed.classes.some((c) => c.id === current)
        ? current
        : (listed.classes[0]?.id ?? null),
    );
    return listed.classes;
  }, []);

  const openImage = useCallback(
    async (id: string) => {
      try {
        const loaded = await getImage(id, filter === "all" ? undefined : filter);
        setDetail(loaded);
        setBoxes(loaded.boxes);
        setSelectedIndex(-1);
        setDrawMode(false);
      } catch (e: unknown) {
        setError(describe(e));
      }
    },
    [filter],
  );

  useEffect(() => {
    void (async () => {
      try {
        await refreshClasses();
        const listed = await refreshImages();
        if (listed[0]) await openImage(listed[0].id);
      } catch (e: unknown) {
        setError(describe(e));
      }
    })();
    // Only on mount: later refreshes are driven by the actions that cause them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reloading the list on a filter change can strand the open image; keep it if
  // it survives the filter, otherwise fall back to the first that does.
  useEffect(() => {
    void (async () => {
      try {
        const listed = await refreshImages();
        if (detail && listed.some((i) => i.id === detail.image.id)) {
          await openImage(detail.image.id);
        } else if (listed[0]) {
          await openImage(listed[0].id);
        } else {
          setDetail(null);
          setBoxes([]);
        }
      } catch (e: unknown) {
        setError(describe(e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const persist = useCallback(
    async (next: DraftBox[], status?: ImageStatus) => {
      if (!detail) return;
      setSaving(true);
      try {
        const saved = await saveBoxes(detail.image.id, next, status);
        setBoxes(saved.boxes);
        setDetail((current) =>
          current ? { ...current, image: saved.image, boxes: saved.boxes } : current,
        );
        await refreshImages();
      } catch (e: unknown) {
        setError(describe(e));
        // The server refused the edit, so show what it actually holds.
        await openImage(detail.image.id);
      } finally {
        setSaving(false);
      }
    },
    [detail, openImage, refreshImages],
  );

  const onBoxesChange = useCallback(
    (next: DraftBox[], committed: boolean) => {
      setBoxes(next);
      if (committed) void persist(next);
    },
    [persist],
  );

  const changeBoxClass = useCallback(
    (index: number, classId: string) => {
      const next = boxes.map((box, i) =>
        i === index ? { ...box, class_id: classId } : box,
      );
      setBoxes(next);
      void persist(next);
    },
    [boxes, persist],
  );

  const deleteBox = useCallback(
    (index: number) => {
      const next = boxes.filter((_, i) => i !== index);
      setBoxes(next);
      setSelectedIndex(-1);
      void persist(next);
    },
    [boxes, persist],
  );

  const step = useCallback(
    (direction: -1 | 1) => {
      const target =
        direction === -1 ? detail?.previous_id : detail?.next_id;
      if (target) void openImage(target);
    },
    [detail, openImage],
  );

  const markDoneAndAdvance = useCallback(async () => {
    if (!detail) return;
    const next = detail.next_id;
    try {
      // Persist the boxes and the status together so an image can never be
      // marked done while an unsaved edit is still on screen.
      await persist(boxes, "done");
    } catch (e: unknown) {
      setError(describe(e));
      return;
    }
    if (next) void openImage(next);
  }, [boxes, detail, openImage, persist]);

  // Keyboard flow. Typing in a field must never trigger a shortcut, so anything
  // originating in an input is ignored outright.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const digit = Number.parseInt(event.key, 10);
      if (!Number.isNaN(digit) && digit >= 1 && digit <= 9) {
        const cls = classes[digit - 1];
        if (!cls) return;
        event.preventDefault();
        if (selectedIndex >= 0) changeBoxClass(selectedIndex, cls.id);
        else setActiveClassId(cls.id);
        return;
      }

      switch (event.key.toLowerCase()) {
        case "w":
          event.preventDefault();
          if (activeClassId) setDrawMode(true);
          break;
        case "a":
          event.preventDefault();
          step(-1);
          break;
        case "d":
          event.preventDefault();
          step(1);
          break;
        case "f":
          event.preventDefault();
          setFitToken((n) => n + 1);
          break;
        case " ":
          event.preventDefault();
          void markDoneAndAdvance();
          break;
        case "delete":
        case "backspace":
          if (selectedIndex >= 0) {
            event.preventDefault();
            deleteBox(selectedIndex);
          }
          break;
        case "escape":
          event.preventDefault();
          setDrawMode(false);
          setSelectedIndex(-1);
          break;
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    activeClassId,
    changeBoxClass,
    classes,
    deleteBox,
    markDoneAndAdvance,
    selectedIndex,
    step,
  ]);

  const statusRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center gap-3 border-b border-line px-3 py-2">
        <span className="text-[13px] font-medium">{project?.name}</span>
        <span
          className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-faint"
          title={project?.path}
        >
          {project?.path}
        </span>

        {saving && (
          <span className="font-mono text-[10px] text-ink-faint">saving…</span>
        )}

        <button
          onClick={() => setImportOpen(true)}
          className="border border-line-strong px-2.5 py-1 text-[12px]
            transition-colors hover:border-accent hover:text-accent"
        >
          Add images
        </button>
        <button
          onClick={() => setLabelsOpen(true)}
          className="border border-line-strong px-2.5 py-1 text-[12px]
            transition-colors hover:border-accent hover:text-accent"
        >
          Import labels
        </button>
        <button
          onClick={() => setExportOpen(true)}
          className="border border-line-strong px-2.5 py-1 text-[12px]
            transition-colors hover:border-accent hover:text-accent"
        >
          Export
        </button>
        <button
          onClick={() => void closeProject().then(() => setProject(null))}
          className="text-[12px] text-ink-muted transition-colors hover:text-ink"
        >
          Close
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-64 shrink-0 flex-col border-r border-line">
          <ImageList
            images={images}
            counts={counts}
            filter={filter}
            currentId={detail?.image.id ?? null}
            onFilterChange={setFilter}
            onSelect={(id) => void openImage(id)}
          />
        </aside>

        <main className="relative min-w-0 flex-1 bg-surface-0">
          {detail ? (
            <BoxCanvas
              imageUrl={imageFileUrl(detail.image.id)}
              imageWidth={detail.image.width}
              imageHeight={detail.image.height}
              boxes={boxes}
              classes={classes}
              selectedIndex={selectedIndex}
              activeClassId={activeClassId}
              drawMode={drawMode}
              onBoxesChange={onBoxesChange}
              onSelect={setSelectedIndex}
              onDrawModeEnd={() => setDrawMode(false)}
              fitToken={fitToken}
            />
          ) : (
            <div className="grid h-full place-items-center px-6 text-center">
              <div>
                <p className="text-ink-muted">No images in this project yet.</p>
                <button
                  onClick={() => setImportOpen(true)}
                  className="mt-3 bg-accent px-4 py-2 text-[13px] font-medium
                    text-surface-0 transition-colors hover:bg-accent-hover"
                >
                  Add images
                </button>
              </div>
            </div>
          )}

          {drawMode && (
            <div
              className="pointer-events-none absolute left-3 top-3 bg-accent px-2 py-1
                font-mono text-[10px] uppercase tracking-wider text-surface-0"
            >
              Drawing
            </div>
          )}
        </main>

        <aside className="flex w-60 shrink-0 flex-col border-l border-line">
          <ClassPalette
            classes={classes}
            activeClassId={activeClassId}
            onActivate={setActiveClassId}
            onCreate={async (name) => {
              try {
                const created = await createClass(name);
                await refreshClasses();
                setActiveClassId(created.id);
              } catch (e: unknown) {
                setError(describe(e));
              }
            }}
            onRename={async (id, name) => {
              try {
                await updateClass(id, { name });
                await refreshClasses();
              } catch (e: unknown) {
                setError(describe(e));
              }
            }}
            onDelete={setDeleteTarget}
          />

          <BoxList
            boxes={boxes}
            classes={classes}
            selectedIndex={selectedIndex}
            onSelect={setSelectedIndex}
            onChangeClass={changeBoxClass}
            onDelete={deleteBox}
          />
        </aside>
      </div>

      <footer
        ref={statusRef}
        className="flex shrink-0 items-center gap-4 border-t border-line px-3 py-1.5
          font-mono text-[10px] text-ink-faint"
      >
        {detail && (
          <>
            <span className="truncate text-ink-muted">{detail.image.filename}</span>
            <span>
              {detail.image.width}×{detail.image.height}
            </span>
            <span>{detail.image.status.replace("_", " ")}</span>
          </>
        )}
        <span className="flex-1" />
        <span className="hidden sm:inline">
          W draw · 1-9 class · A/D prev/next · Space done · Del remove · F fit
        </span>
      </footer>

      <ImportImagesDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={async () => {
          const listed = await refreshImages();
          if (!detail && listed[0]) await openImage(listed[0].id);
        }}
      />

      <ImportLabelsDialog
        open={labelsOpen}
        classes={classes}
        onClose={() => setLabelsOpen(false)}
        onImported={async () => {
          await refreshClasses();
          await refreshImages();
          if (detail) await openImage(detail.image.id);
        }}
      />

      <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} />

      <DeleteClassDialog
        target={deleteTarget}
        classes={classes}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async (classId, reassignTo) => {
          try {
            await deleteClass(classId, reassignTo);
            await refreshClasses();
            await refreshImages();
            if (detail) await openImage(detail.image.id);
          } catch (e: unknown) {
            setError(describe(e));
          } finally {
            setDeleteTarget(null);
          }
        }}
      />

      {error && (
        <div
          role="alert"
          className="absolute bottom-10 left-1/2 flex -translate-x-1/2 items-center
            gap-3 border border-status-review bg-surface-1 px-4 py-2.5 text-[12px]"
        >
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            aria-label="Dismiss"
            className="text-ink-faint hover:text-ink"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
