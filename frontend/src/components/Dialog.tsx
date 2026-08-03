import { useEffect, useRef, type ReactNode } from "react";

/**
 * A modal built on the native <dialog> element, which brings focus trapping,
 * Escape handling and inertness of the page behind it without reimplementing any
 * of it.
 */
export function Dialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      className="m-auto w-[min(30rem,calc(100vw-2rem))] border border-line-strong
        bg-surface-1 p-0 text-ink backdrop:bg-black/60"
    >
      <div className="flex items-baseline justify-between border-b border-line px-4 py-3">
        <h2 className="text-[13px] font-medium">{title}</h2>
        <button
          onClick={onClose}
          aria-label="Close"
          className="text-ink-faint transition-colors hover:text-ink"
        >
          ×
        </button>
      </div>
      <div className="px-4 py-4">{children}</div>
    </dialog>
  );
}
