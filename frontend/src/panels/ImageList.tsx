import type { ImageRecord, ImageStatus, StatusCounts } from "../api/labeling";

const STATUS_COLOR: Record<ImageStatus, string> = {
  unlabeled: "bg-status-unlabeled",
  in_progress: "bg-status-progress",
  done: "bg-status-done",
  needs_review: "bg-status-review",
};

const FILTERS: { id: ImageStatus | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "unlabeled", label: "Todo" },
  { id: "in_progress", label: "Doing" },
  { id: "done", label: "Done" },
  { id: "needs_review", label: "Review" },
];

export function ImageList({
  images,
  counts,
  filter,
  currentId,
  onFilterChange,
  onSelect,
}: {
  images: ImageRecord[];
  counts: StatusCounts;
  filter: ImageStatus | "all";
  currentId: string | null;
  onFilterChange: (filter: ImageStatus | "all") => void;
  onSelect: (id: string) => void;
}) {
  const countFor = (id: ImageStatus | "all") =>
    id === "all" ? counts.total : counts[id];

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap gap-1 border-b border-line p-2">
        {FILTERS.map((entry) => {
          const active = filter === entry.id;
          return (
            <button
              key={entry.id}
              onClick={() => onFilterChange(entry.id)}
              className={`px-2 py-1 font-mono text-[10px] uppercase tracking-wider
                transition-colors focus-visible:outline focus-visible:outline-2
                focus-visible:-outline-offset-2 focus-visible:outline-accent ${
                  active
                    ? "bg-surface-3 text-ink"
                    : "text-ink-faint hover:text-ink-muted"
                }`}
            >
              {entry.label}
              <span className="ml-1.5 opacity-60">{countFor(entry.id)}</span>
            </button>
          );
        })}
      </div>

      <ul className="flex-1 overflow-y-auto">
        {images.map((image) => {
          const current = image.id === currentId;
          return (
            <li key={image.id}>
              <button
                onClick={() => onSelect(image.id)}
                className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left
                  transition-colors focus-visible:outline focus-visible:outline-2
                  focus-visible:-outline-offset-2 focus-visible:outline-accent ${
                    current ? "bg-surface-3" : "hover:bg-surface-1"
                  }`}
              >
                <span
                  aria-hidden
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    STATUS_COLOR[image.status]
                  }`}
                />
                <span
                  className={`min-w-0 flex-1 truncate text-[12px] ${
                    current ? "text-ink" : "text-ink-muted"
                  }`}
                  title={image.filename}
                >
                  {image.filename}
                </span>
                {image.annotation_count > 0 && (
                  <span className="shrink-0 font-mono text-[10px] text-ink-faint">
                    {image.annotation_count}
                  </span>
                )}
              </button>
            </li>
          );
        })}

        {images.length === 0 && (
          <li className="px-3 py-6 text-center text-[12px] text-ink-faint">
            Nothing here.
          </li>
        )}
      </ul>
    </div>
  );
}
