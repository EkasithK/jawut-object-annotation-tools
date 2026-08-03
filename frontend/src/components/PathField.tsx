import { useEffect, useState } from "react";

import { browse, nativeDialogsAvailable, type BrowseKind } from "../api/system";

/**
 * A path input with a native Browse button beside it.
 *
 * The button only appears when the app is running in its desktop window, since
 * that is the only place a native dialog exists. Everywhere else — a dev server
 * in a browser, a headless build — the field is still typeable, so no flow is
 * ever blocked by the button being absent.
 */
export function PathField({
  id,
  label,
  value,
  onChange,
  placeholder,
  kind = "folder",
  size = "sm",
  hint,
  autoFocus = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  kind?: BrowseKind;
  size?: "sm" | "md";
  hint?: string;
  autoFocus?: boolean;
}) {
  const [available, setAvailable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void nativeDialogsAvailable().then((ok) => {
      if (live) setAvailable(ok);
    });
    return () => {
      live = false;
    };
  }, []);

  async function pick() {
    setError(null);
    try {
      // Opening where the field already points saves re-navigating the tree.
      const chosen = await browse(kind, value.trim());
      if (chosen !== null) onChange(chosen);
    } catch {
      setError("Could not open the file browser — type the path instead.");
      setAvailable(false);
    }
  }

  const input =
    size === "md"
      ? `bg-surface-1 px-3 py-2.5 text-[12px]`
      : `bg-surface-2 px-2.5 py-2 text-[12px]`;

  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1.5 block text-[11px] uppercase tracking-wider text-ink-muted"
      >
        {label}
      </label>

      <div className="flex gap-2">
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          spellCheck={false}
          autoFocus={autoFocus}
          className={`min-w-0 flex-1 border border-line font-mono text-ink
            transition-colors placeholder:text-ink-faint hover:border-line-strong
            focus:border-accent focus:outline-none ${input}`}
        />

        {available && (
          <button
            type="button"
            onClick={() => void pick()}
            className="shrink-0 border border-line-strong px-3 text-[12px]
              transition-colors hover:border-accent hover:text-accent
              focus-visible:outline focus-visible:outline-2
              focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Browse…
          </button>
        )}
      </div>

      {hint && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-ink-faint">{hint}</p>
      )}
      {error && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-status-review">
          {error}
        </p>
      )}
    </div>
  );
}
