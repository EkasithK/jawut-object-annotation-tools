import { useState } from "react";

import { ApiError } from "../api/client";
import {
  applyLabels,
  previewLabels,
  REPAIR_KINDS,
  type ImportIssue,
  type LabelImportResult,
  type LabelPreview,
} from "../api/labelImport";
import { createClass, type ObjectClass } from "../api/labeling";
import { Dialog } from "./Dialog";

/** `null` ignores the class; `NEW` creates one named after the source class. */
const NEW = "__new__";

type Step = "choose" | "map" | "done";

export function ImportLabelsDialog({
  open,
  classes,
  onClose,
  onImported,
}: {
  open: boolean;
  classes: ObjectClass[];
  onClose: () => void;
  onImported: () => Promise<void>;
}) {
  const [step, setStep] = useState<Step>("choose");
  const [labelsDir, setLabelsDir] = useState("");
  const [overwrite, setOverwrite] = useState(true);
  const [preview, setPreview] = useState<LabelPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<LabelImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const describe = (e: unknown) =>
    e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);

  function reset() {
    setStep("choose");
    setPreview(null);
    setMapping({});
    setResult(null);
    setError(null);
  }

  async function runPreview(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const found = await previewLabels(labelsDir.trim());
      setPreview(found);
      // Pre-select by name so an identical taxonomy needs no clicks at all.
      const initial: Record<string, string> = {};
      found.source_classes.names.forEach((name, index) => {
        const match = classes.find(
          (c) => c.name.toLowerCase() === name.toLowerCase(),
        );
        initial[String(index)] = match ? match.id : NEW;
      });
      setMapping(initial);
      setStep("map");
    } catch (e: unknown) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  async function runImport() {
    if (!preview) return;
    setError(null);
    setBusy(true);
    try {
      // Create the classes marked "new" first, so the mapping can reference them.
      const resolved: Record<string, string | null> = {};
      for (const [index, choice] of Object.entries(mapping)) {
        if (choice === NEW) {
          const name = preview.source_classes.names[Number(index)];
          if (!name) continue;
          const existing = classes.find(
            (c) => c.name.toLowerCase() === name.toLowerCase(),
          );
          resolved[index] = existing
            ? existing.id
            : (await createClass(name)).id;
        } else {
          resolved[index] = choice === "" ? null : choice;
        }
      }

      setResult(await applyLabels(labelsDir.trim(), resolved, overwrite));
      await onImported();
      setStep("done");
    } catch (e: unknown) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  function close() {
    reset();
    onClose();
  }

  return (
    <Dialog open={open} title="Import labels" onClose={close}>
      {step === "choose" && (
        <form onSubmit={(e) => void runPreview(e)}>
          <label
            htmlFor="labels-dir"
            className="mb-1.5 block text-[11px] uppercase tracking-wider text-ink-muted"
          >
            Folder of .txt labels
          </label>
          <input
            id="labels-dir"
            value={labelsDir}
            onChange={(e) => setLabelsDir(e.target.value)}
            placeholder="C:\datasets\helmet\labels"
            spellCheck={false}
            autoFocus
            className="w-full border border-line bg-surface-2 px-2.5 py-2 font-mono
              text-[12px] placeholder:text-ink-faint focus:border-accent
              focus:outline-none"
          />
          <p className="mt-2 text-[11px] leading-relaxed text-ink-faint">
            Labels match images by filename. A <code>data.yaml</code> beside the
            folder or one level up is read for class names.
          </p>

          <button
            type="submit"
            disabled={busy || !labelsDir.trim()}
            className="mt-4 w-full bg-accent px-3 py-2 text-[13px] font-medium
              text-surface-0 transition-colors hover:bg-accent-hover
              disabled:bg-surface-3 disabled:text-ink-faint"
          >
            {busy ? "Reading…" : "Read folder"}
          </button>
        </form>
      )}

      {step === "map" && preview && (
        <>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
            <Stat label="Label files" value={preview.label_files} />
            <Stat label="Matched images" value={preview.matched_images} />
            <Stat
              label="Images without labels"
              value={preview.images_without_labels}
            />
            <Stat
              label="Unmatched labels"
              value={preview.unmatched_labels.length}
              warn={preview.unmatched_labels.length > 0}
            />
          </dl>

          <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
            Map classes
            {!preview.source_classes.from_data_yaml && " · no data.yaml found"}
          </p>

          <ul className="mt-2 border border-line">
            {preview.source_classes.names.map((name, index) => (
              <li
                key={index}
                className="flex items-center gap-2 border-b border-line px-2 py-1.5
                  last:border-b-0"
              >
                <span className="w-6 shrink-0 font-mono text-[11px] text-ink-faint">
                  {index}
                </span>
                <span className="min-w-0 flex-1 truncate text-[12px]">{name}</span>
                <span className="shrink-0 font-mono text-[10px] text-ink-faint">
                  {preview.box_counts[String(index)] ?? 0}
                </span>
                <span aria-hidden className="text-ink-faint">
                  →
                </span>
                <select
                  value={mapping[String(index)] ?? ""}
                  onChange={(e) =>
                    setMapping({ ...mapping, [String(index)]: e.target.value })
                  }
                  aria-label={`Map class ${name}`}
                  className="w-40 shrink-0 border border-line bg-surface-2 px-1.5 py-1
                    text-[12px] focus:border-accent focus:outline-none"
                >
                  <option value={NEW}>Create “{name}”</option>
                  {classes.map((cls) => (
                    <option key={cls.id} value={cls.id}>
                      {cls.name}
                    </option>
                  ))}
                  <option value="">Ignore</option>
                </select>
              </li>
            ))}
          </ul>

          <label className="mt-3 flex items-center gap-2 text-[12px]">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
              className="accent-accent"
            />
            Replace boxes on images that already have some
          </label>

          <IssueList issues={preview.issues} />

          <div className="mt-4 flex gap-2">
            <button
              onClick={() => setStep("choose")}
              className="border border-line-strong px-3 py-2 text-[13px]
                transition-colors hover:border-accent"
            >
              Back
            </button>
            <button
              disabled={busy || preview.matched_images === 0}
              onClick={() => void runImport()}
              className="flex-1 bg-accent px-3 py-2 text-[13px] font-medium
                text-surface-0 transition-colors hover:bg-accent-hover
                disabled:bg-surface-3 disabled:text-ink-faint"
            >
              {busy ? "Importing…" : `Import ${preview.matched_images} images`}
            </button>
          </div>
        </>
      )}

      {step === "done" && result && (
        <>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
            <Stat label="Images labeled" value={result.images_labeled} />
            <Stat label="Boxes created" value={result.boxes_created} />
            <Stat label="Marked empty" value={result.images_marked_empty} />
            <Stat
              label="Boxes ignored"
              value={result.skipped_boxes}
              warn={result.skipped_boxes > 0}
            />
          </dl>

          <IssueList issues={result.issues} />

          <button
            onClick={close}
            className="mt-4 w-full bg-accent px-3 py-2 text-[13px] font-medium
              text-surface-0 transition-colors hover:bg-accent-hover"
          >
            Done
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
  value: number;
  warn?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-line py-1">
      <dt className="text-ink-muted">{label}</dt>
      <dd className={`font-mono ${warn ? "text-status-review" : "text-ink"}`}>
        {value}
      </dd>
    </div>
  );
}

function IssueList({ issues }: { issues: ImportIssue[] }) {
  if (issues.length === 0) return null;

  const repairs = issues.filter((i) => REPAIR_KINDS.has(i.kind));
  const rejections = issues.filter((i) => !REPAIR_KINDS.has(i.kind));

  return (
    <details className="mt-3 border border-line">
      <summary className="cursor-pointer px-2 py-1.5 text-[12px] text-ink-muted">
        {rejections.length > 0 && (
          <span className="text-status-review">{rejections.length} rejected</span>
        )}
        {rejections.length > 0 && repairs.length > 0 && " · "}
        {repairs.length > 0 && <span>{repairs.length} repaired</span>}
      </summary>
      <ul className="max-h-48 overflow-y-auto border-t border-line">
        {issues.map((issue, index) => (
          <li
            key={`${issue.file}-${issue.line}-${index}`}
            className="border-b border-line px-2 py-1.5 font-mono text-[11px]
              last:border-b-0"
          >
            <span className={REPAIR_KINDS.has(issue.kind) ? "text-ink-muted" : ""}>
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
  );
}
