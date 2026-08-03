import type { ReactNode } from "react";

/**
 * A bounding box, rendered as chrome.
 *
 * The corner brackets and the attached label chip are the exact marks this tool
 * draws on an image, so the interface is built out of its own subject matter.
 * Used sparingly — the wordmark and the primary surfaces only.
 */
export function Frame({
  label,
  children,
  active = false,
  className = "",
}: {
  label?: string;
  children: ReactNode;
  active?: boolean;
  className?: string;
}) {
  const corner = active ? "border-accent" : "border-line-strong";

  return (
    <div className={`relative ${className}`}>
      {label && (
        <span
          className={`absolute -top-[9px] left-3 z-10 px-1.5 font-mono text-[10px]
            uppercase tracking-[0.14em] ${
              active ? "text-accent" : "text-ink-faint"
            } bg-surface-0`}
        >
          {label}
        </span>
      )}

      <span
        aria-hidden
        className={`pointer-events-none absolute -left-px -top-px h-3 w-3 border-l-2 border-t-2 ${corner} transition-colors`}
      />
      <span
        aria-hidden
        className={`pointer-events-none absolute -right-px -top-px h-3 w-3 border-r-2 border-t-2 ${corner} transition-colors`}
      />
      <span
        aria-hidden
        className={`pointer-events-none absolute -bottom-px -left-px h-3 w-3 border-b-2 border-l-2 ${corner} transition-colors`}
      />
      <span
        aria-hidden
        className={`pointer-events-none absolute -bottom-px -right-px h-3 w-3 border-b-2 border-r-2 ${corner} transition-colors`}
      />

      {children}
    </div>
  );
}
