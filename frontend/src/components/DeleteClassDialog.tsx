import { useEffect, useState } from "react";

import { classUsage, type ClassUsage, type ObjectClass } from "../api/labeling";
import { Dialog } from "./Dialog";

/**
 * Deleting a class is the one destructive action in the tool, so the dialog
 * states the exact cost before offering the two ways out: move the boxes
 * somewhere, or lose them.
 */
export function DeleteClassDialog({
  target,
  classes,
  onCancel,
  onConfirm,
}: {
  target: ObjectClass | null;
  classes: ObjectClass[];
  onCancel: () => void;
  onConfirm: (classId: string, reassignTo: string | null) => Promise<void>;
}) {
  const [usage, setUsage] = useState<ClassUsage | null>(null);
  const [reassignTo, setReassignTo] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const alternatives = classes.filter((c) => c.id !== target?.id);

  useEffect(() => {
    if (!target) {
      setUsage(null);
      return;
    }
    setReassignTo(alternatives[0]?.id ?? "");
    let cancelled = false;
    classUsage(target.id)
      .then((result) => {
        if (!cancelled) setUsage(result);
      })
      .catch(() => {
        if (!cancelled) setUsage(null);
      });
    return () => {
      cancelled = true;
    };
    // Recomputing on `alternatives` would refetch on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  async function confirm(destination: string | null) {
    if (!target) return;
    setBusy(true);
    try {
      await onConfirm(target.id, destination);
    } finally {
      setBusy(false);
    }
  }

  const inUse = (usage?.annotations ?? 0) > 0;

  return (
    <Dialog
      open={target !== null}
      title={`Delete “${target?.name ?? ""}”`}
      onClose={onCancel}
    >
      {usage === null ? (
        <p className="text-ink-muted">Checking where this class is used…</p>
      ) : inUse ? (
        <>
          <p className="text-[13px] leading-relaxed">
            <span className="font-mono">{usage.annotations}</span>{" "}
            {usage.annotations === 1 ? "box" : "boxes"} across{" "}
            <span className="font-mono">{usage.images}</span>{" "}
            {usage.images === 1 ? "image" : "images"} use this class.
          </p>

          {alternatives.length > 0 && (
            <div className="mt-4">
              <label
                htmlFor="reassign-target"
                className="mb-1.5 block text-[11px] uppercase tracking-wider
                  text-ink-muted"
              >
                Move those boxes to
              </label>
              <select
                id="reassign-target"
                value={reassignTo}
                onChange={(e) => setReassignTo(e.target.value)}
                className="w-full border border-line bg-surface-2 px-2.5 py-2
                  text-[13px] focus:border-accent focus:outline-none"
              >
                {alternatives.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-2">
            {alternatives.length > 0 && (
              <button
                disabled={busy || !reassignTo}
                onClick={() => void confirm(reassignTo)}
                className="flex-1 bg-accent px-3 py-2 text-[13px] font-medium
                  text-on-accent transition-colors hover:bg-accent-hover
                  disabled:bg-surface-3 disabled:text-ink-faint"
              >
                Move and delete
              </button>
            )}
            <button
              disabled={busy}
              onClick={() => void confirm(null)}
              className="flex-1 border border-status-review px-3 py-2 text-[13px]
                text-status-review transition-colors hover:bg-status-review
                hover:text-on-accent disabled:opacity-50"
            >
              Delete {usage.annotations} {usage.annotations === 1 ? "box" : "boxes"}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="text-[13px] leading-relaxed text-ink-muted">
            No boxes use this class, so nothing else changes.
          </p>
          <button
            disabled={busy}
            onClick={() => void confirm(null)}
            className="mt-5 w-full bg-accent px-3 py-2 text-[13px] font-medium
              text-on-accent transition-colors hover:bg-accent-hover
              disabled:opacity-50"
          >
            Delete class
          </button>
        </>
      )}
    </Dialog>
  );
}
