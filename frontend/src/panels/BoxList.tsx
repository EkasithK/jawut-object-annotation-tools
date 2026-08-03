import type { DraftBox, ObjectClass } from "../api/labeling";

export function BoxList({
  boxes,
  classes,
  selectedIndex,
  onSelect,
  onChangeClass,
  onDelete,
}: {
  boxes: DraftBox[];
  classes: ObjectClass[];
  selectedIndex: number;
  onSelect: (index: number) => void;
  onChangeClass: (index: number, classId: string) => void;
  onDelete: (index: number) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col border-t border-line">
      <h2
        className="px-3 py-2 font-mono text-[10px] uppercase tracking-[0.18em]
          text-ink-faint"
      >
        Boxes
        <span className="ml-1.5 opacity-60">{boxes.length}</span>
      </h2>

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {boxes.map((box, index) => {
          const cls = classes.find((c) => c.id === box.class_id);
          const selected = index === selectedIndex;
          return (
            <li
              key={box.id ?? `draft-${index}`}
              className={`group flex items-center gap-2 px-2.5 py-1.5 ${
                selected ? "bg-surface-3" : "hover:bg-surface-1"
              }`}
            >
              <span
                aria-hidden
                className="h-2.5 w-2.5 shrink-0"
                style={{ background: cls?.color ?? "#8a94a6" }}
              />

              <select
                value={box.class_id}
                onChange={(e) => onChangeClass(index, e.target.value)}
                onFocus={() => onSelect(index)}
                onKeyDown={(e) => e.stopPropagation()}
                aria-label={`Class of box ${index + 1}`}
                className="min-w-0 flex-1 cursor-pointer border-none bg-transparent
                  text-[12px] text-ink focus:outline-none"
              >
                {classes.map((option) => (
                  <option key={option.id} value={option.id} className="bg-surface-2">
                    {option.name}
                  </option>
                ))}
              </select>

              <button
                onClick={() => onDelete(index)}
                aria-label={`Delete box ${index + 1}`}
                className="shrink-0 px-1 text-ink-faint opacity-0 transition
                  hover:text-status-review focus-visible:opacity-100
                  group-hover:opacity-100"
              >
                ×
              </button>
            </li>
          );
        })}

        {boxes.length === 0 && (
          <li className="px-3 py-4 text-[11px] leading-relaxed text-ink-faint">
            No boxes yet. Press <Key>W</Key> and drag to draw one.
          </li>
        )}
      </ul>
    </div>
  );
}

function Key({ children }: { children: React.ReactNode }) {
  return (
    <kbd
      className="border border-line-strong px-1 font-mono text-[10px] text-ink-muted"
    >
      {children}
    </kbd>
  );
}
