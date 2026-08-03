import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import {
  adoptDataset,
  LAYOUT_LABELS,
  scanDataset,
  type AdoptResult,
  type DatasetScan,
} from "../api/datasets";
import type { ProjectSummary } from "../api/projects";
import { Dialog } from "./Dialog";
import { PathField } from "./PathField";

type Step = "choose" | "confirm" | "done";

/**
 * Turns a folder someone was handed into a project in one pass.
 *
 * The point of the middle step is that nobody has to know the shape of their own
 * data in advance: the folder is read, what was found is shown in plain terms,
 * and the same button finishes the job whether that turned out to be a labeled
 * dataset or a pile of unlabeled photos.
 */
export function OpenDatasetDialog({
  open,
  defaultParentDir,
  onClose,
  onOpened,
}: {
  open: boolean;
  defaultParentDir: string;
  onClose: () => void;
  onOpened: (project: ProjectSummary) => void;
}) {
  const [step, setStep] = useState<Step>("choose");
  const [source, setSource] = useState("");
  const [name, setName] = useState("");
  const [parentDir, setParentDir] = useState(defaultParentDir);
  const [copyImages, setCopyImages] = useState(true);
  const [scan, setScan] = useState<DatasetScan | null>(null);
  const [result, setResult] = useState<AdoptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The welcome screen learns the default location from the server after this
  // component has already mounted, so the initial state misses it. Re-seeding on
  // open also means a second visit starts clean rather than in the last state.
  useEffect(() => {
    if (open) setParentDir(defaultParentDir);
  }, [open, defaultParentDir]);

  const describe = (e: unknown) =>
    e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);

  /** The folder's own name is almost always the right project name. */
  function suggestName(path: string): string {
    const parts = path.split(/[\\/]/).filter(Boolean);
    return parts[parts.length - 1] ?? "";
  }

  async function runScan(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const found = await scanDataset(source.trim());
      setScan(found);
      if (!name.trim()) setName(suggestName(source.trim()));
      setStep("confirm");
    } catch (e: unknown) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  async function runAdopt() {
    setError(null);
    setBusy(true);
    try {
      setResult(
        await adoptDataset(
          source.trim(),
          name.trim(),
          parentDir.trim() || defaultParentDir,
          copyImages,
        ),
      );
      setStep("done");
    } catch (e: unknown) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  function close() {
    setStep("choose");
    setScan(null);
    setResult(null);
    setError(null);
    onClose();
  }

  const nothingFound = scan !== null && scan.image_count === 0;

  return (
    <Dialog open={open} title="Open existing dataset" onClose={close}>
      {step === "choose" && (
        <form onSubmit={(e) => void runScan(e)}>
          <PathField
            id="dataset-source"
            label="Dataset folder"
            value={source}
            onChange={setSource}
            placeholder="C:\datasets\helmet"
            hint="The folder holding your images — with or without labels beside
              them. Nothing in it is modified."
            autoFocus
          />

          <button
            type="submit"
            disabled={busy || !source.trim()}
            className="mt-4 w-full bg-accent px-3 py-2 text-[13px] font-medium
              text-on-accent transition-colors hover:bg-accent-hover
              disabled:bg-surface-3 disabled:text-ink-faint"
          >
            {busy ? "Reading…" : "Read folder"}
          </button>
        </form>
      )}

      {step === "confirm" && scan && (
        <>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
            Found in {scan.root}
          </p>

          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
            <Stat label="Images" value={scan.image_count.toLocaleString()} />
            <Stat label="Label files" value={scan.label_count.toLocaleString()} />
            <Stat
              label="Classes"
              value={scan.class_names.length || "none named"}
              warn={scan.label_count > 0 && scan.class_names.length === 0}
            />
            {/* Full width: the layout names are long enough to truncate in a
                half-width cell, and that is the one value nobody can guess. */}
            <div className="col-span-2">
              <Stat label="Layout" value={LAYOUT_LABELS[scan.layout]} />
            </div>
          </dl>

          {scan.class_names.length > 0 && (
            <p className="mt-2 text-[12px] leading-relaxed text-ink-muted">
              {scan.class_names.join(", ")}
            </p>
          )}

          {scan.label_count > 0 && scan.class_names.length === 0 && (
            <p className="mt-2 text-[11px] leading-relaxed text-status-progress">
              No data.yaml was found, so classes will arrive as class_0, class_1, …
              You can rename them afterwards without touching any labels.
            </p>
          )}

          {nothingFound ? (
            <p className="mt-4 border-l-2 border-status-review bg-surface-2 px-3
              py-2 text-[12px] leading-relaxed">
              There are no images in this folder. Pick a different one, or close
              this and use New project to start empty.
            </p>
          ) : (
            <div className="mt-4 space-y-3 border-t border-line pt-4">
              <div>
                <label
                  htmlFor="dataset-name"
                  className="mb-1.5 block text-[11px] uppercase tracking-wider
                    text-ink-muted"
                >
                  Project name
                </label>
                <input
                  id="dataset-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  spellCheck={false}
                  className="w-full border border-line bg-surface-2 px-2.5 py-2
                    text-[12px] focus:border-accent focus:outline-none"
                />
              </div>

              <PathField
                id="dataset-parent"
                label="Create the project in"
                value={parentDir}
                onChange={setParentDir}
              />

              <label className="flex items-center gap-2 text-[12px]">
                <input
                  type="checkbox"
                  checked={copyImages}
                  onChange={(e) => setCopyImages(e.target.checked)}
                  className="accent-accent"
                />
                Copy the images into the project
              </label>
              <p className="ml-6 -mt-2 text-[11px] leading-relaxed text-ink-faint">
                Keeps the project self-contained and leaves the original folder
                untouched. Turn off for very large sets.
              </p>
            </div>
          )}

          <div className="mt-4 flex gap-2">
            <button
              onClick={() => setStep("choose")}
              className="border border-line-strong px-3 py-2 text-[13px]
                transition-colors hover:border-accent"
            >
              Back
            </button>
            <button
              disabled={busy || nothingFound || !name.trim()}
              onClick={() => void runAdopt()}
              className="flex-1 bg-accent px-3 py-2 text-[13px] font-medium
                text-on-accent transition-colors hover:bg-accent-hover
                disabled:bg-surface-3 disabled:text-ink-faint"
            >
              {busy ? "Building the project…" : "Create project from this"}
            </button>
          </div>
        </>
      )}

      {step === "done" && result && (
        <>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
            <Stat label="Images" value={result.images_imported.toLocaleString()} />
            <Stat label="Classes" value={result.classes_created} />
            <Stat label="Boxes" value={result.boxes_created.toLocaleString()} />
            <Stat
              label="Images labeled"
              value={result.images_labeled.toLocaleString()}
            />
            {result.images_marked_empty > 0 && (
              <Stat
                label="Marked empty"
                value={result.images_marked_empty.toLocaleString()}
              />
            )}
            {result.images_skipped > 0 && (
              <Stat label="Skipped" value={result.images_skipped} warn />
            )}
          </dl>

          {result.issues.length > 0 && (
            <details className="mt-3 border border-line">
              <summary className="cursor-pointer px-2 py-1.5 text-[12px] text-ink-muted">
                {result.issues.length} lines needed attention
              </summary>
              <ul className="max-h-40 overflow-y-auto border-t border-line">
                {result.issues.slice(0, 200).map((issue, index) => (
                  <li
                    key={`${issue.file}-${issue.line}-${index}`}
                    className="border-b border-line px-2 py-1.5 font-mono text-[11px]
                      last:border-b-0"
                  >
                    <span>
                      {issue.file}
                      {issue.line !== null && `:${issue.line}`}
                    </span>
                    <span className="block text-ink-faint">
                      {issue.kind} — {issue.detail}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <button
            onClick={() => {
              const project = result.project;
              close();
              onOpened(project);
            }}
            className="mt-4 w-full bg-accent px-3 py-2 text-[13px] font-medium
              text-on-accent transition-colors hover:bg-accent-hover"
          >
            Start labeling
          </button>
        </>
      )}

      {error && (
        <p className="mt-4 border-l-2 border-status-review bg-surface-2 px-3 py-2 text-[12px]">
          {error}
        </p>
      )}
    </Dialog>
  );
}

function Stat({
  label,
  value,
  warn = false,
}: {
  label: string;
  value: string | number;
  warn?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1">
      <dt className="shrink-0 text-ink-muted">{label}</dt>
      <dd
        className={`min-w-0 truncate text-right font-mono ${
          warn ? "text-status-review" : "text-ink"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
