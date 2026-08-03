import { useState } from "react";

import { importImages, type ImportResult } from "../api/labeling";
import { ApiError } from "../api/client";
import { Dialog } from "./Dialog";

export function ImportImagesDialog({
  open,
  onClose,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  onImported: () => Promise<void>;
}) {
  const [source, setSource] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [copyIntoProject, setCopyIntoProject] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const imported = await importImages(source.trim(), {
        recursive,
        copyIntoProject,
      });
      setResult(imported);
      await onImported();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function close() {
    setResult(null);
    setError(null);
    onClose();
  }

  return (
    <Dialog open={open} title="Add images" onClose={close}>
      <form onSubmit={(e) => void submit(e)}>
        <label
          htmlFor="import-source"
          className="mb-1.5 block text-[11px] uppercase tracking-wider text-ink-muted"
        >
          Folder
        </label>
        <input
          id="import-source"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="C:\datasets\helmet\images"
          spellCheck={false}
          autoFocus
          className="w-full border border-line bg-surface-2 px-2.5 py-2 font-mono
            text-[12px] placeholder:text-ink-faint focus:border-accent
            focus:outline-none"
        />

        <div className="mt-3 space-y-2">
          <Check
            id="import-recursive"
            checked={recursive}
            onChange={setRecursive}
            label="Include subfolders"
          />
          <Check
            id="import-copy"
            checked={copyIntoProject}
            onChange={setCopyIntoProject}
            label="Copy into the project"
            hint="Keeps the project self-contained. Turn off to leave very large sets where they are."
          />
        </div>

        <button
          type="submit"
          disabled={busy || !source.trim()}
          className="mt-4 w-full bg-accent px-3 py-2 text-[13px] font-medium
            text-surface-0 transition-colors hover:bg-accent-hover
            disabled:bg-surface-3 disabled:text-ink-faint"
        >
          {busy ? "Importing…" : "Import"}
        </button>
      </form>

      {error && (
        <p className="mt-4 border-l-2 border-status-review bg-surface-2 px-3 py-2 text-[12px]">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-4 border-t border-line pt-4 text-[12px]">
          <p>
            Imported <span className="font-mono">{result.imported}</span>
            {result.duplicates > 0 && (
              <>
                {" · "}
                <span className="font-mono">{result.duplicates}</span> already in the
                project
              </>
            )}
            {result.skipped.length > 0 && (
              <>
                {" · "}
                <span className="font-mono text-status-review">
                  {result.skipped.length}
                </span>{" "}
                skipped
              </>
            )}
          </p>

          {result.skipped.length > 0 && (
            <ul className="mt-2 max-h-40 overflow-y-auto border border-line bg-surface-2">
              {result.skipped.map((entry) => (
                <li
                  key={entry.path}
                  className="border-b border-line px-2 py-1.5 font-mono text-[11px]
                    last:border-b-0"
                >
                  <span className="text-ink">{entry.path}</span>
                  <span className="block text-ink-faint">{entry.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Dialog>
  );
}

function Check({
  id,
  checked,
  onChange,
  label,
  hint,
}: {
  id: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="flex items-center gap-2 text-[12px]">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="accent-accent"
        />
        {label}
      </label>
      {hint && (
        <p className="ml-6 mt-0.5 text-[11px] leading-relaxed text-ink-faint">
          {hint}
        </p>
      )}
    </div>
  );
}
