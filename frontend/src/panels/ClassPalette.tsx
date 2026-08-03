import { useState } from "react";

import type { ObjectClass } from "../api/labeling";

export function ClassPalette({
  classes,
  activeClassId,
  onActivate,
  onCreate,
  onRename,
  onDelete,
}: {
  classes: ObjectClass[];
  activeClassId: string | null;
  onActivate: (id: string) => void;
  onCreate: (name: string) => Promise<void>;
  onRename: (id: string, name: string) => Promise<void>;
  onDelete: (cls: ObjectClass) => void;
}) {
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  async function submitNew(event: React.FormEvent) {
    event.preventDefault();
    const name = draft.trim();
    if (!name) return;
    await onCreate(name);
    setDraft("");
  }

  async function submitRename(event: React.FormEvent, id: string) {
    event.preventDefault();
    const name = editValue.trim();
    if (name) await onRename(id, name);
    setEditing(null);
  }

  return (
    <div className="flex flex-col">
      <h2
        className="px-3 py-2 font-mono text-[12px] uppercase tracking-[0.18em] font-medium
          text-ink-faint"
      >
        Classes
      </h2>

      <ul>
        {classes.map((cls, index) => {
          const active = cls.id === activeClassId;
          return (
            <li key={cls.id} className="group flex items-stretch">
              {editing === cls.id ? (
                <form
                  onSubmit={(e) => void submitRename(e, cls.id)}
                  className="flex-1 px-2.5 py-1"
                >
                  <input
                    autoFocus
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onBlur={() => setEditing(null)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") setEditing(null);
                      e.stopPropagation();
                    }}
                    className="w-full border border-accent bg-surface-1 px-1.5 py-0.5
                      text-[13px] focus:outline-none"
                  />
                </form>
              ) : (
                <>
                  <button
                    onClick={() => onActivate(cls.id)}
                    onDoubleClick={() => {
                      setEditing(cls.id);
                      setEditValue(cls.name);
                    }}
                    title="Click to make active, double-click to rename"
                    className={`flex min-w-0 flex-1 items-center gap-2 px-2.5 py-1.5
                      text-left transition-colors focus-visible:outline
                      focus-visible:outline-2 focus-visible:-outline-offset-2
                      focus-visible:outline-accent ${
                        active ? "bg-surface-3" : "hover:bg-surface-1"
                      }`}
                  >
                    <span
                      aria-hidden
                      className="h-2.5 w-2.5 shrink-0"
                      style={{ background: cls.color }}
                    />
                    <span className="min-w-0 flex-1 truncate text-[13px]">
                      {cls.name}
                    </span>
                    {index < 9 && (
                      <kbd
                        className="shrink-0 font-mono text-[12px] text-ink-faint"
                        title={`Press ${index + 1} to assign this class`}
                      >
                        {index + 1}
                      </kbd>
                    )}
                  </button>

                  <button
                    onClick={() => onDelete(cls)}
                    aria-label={`Delete class ${cls.name}`}
                    title="Delete class"
                    className="px-2 text-ink-faint opacity-0 transition
                      hover:text-status-review focus-visible:opacity-100
                      focus-visible:outline focus-visible:outline-2
                      focus-visible:-outline-offset-2 focus-visible:outline-accent
                      group-hover:opacity-100"
                  >
                    ×
                  </button>
                </>
              )}
            </li>
          );
        })}
      </ul>

      <form onSubmit={(e) => void submitNew(e)} className="p-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.stopPropagation()}
          placeholder="Add a class…"
          spellCheck={false}
          className="w-full border border-line bg-surface-1 px-2 py-1.5 text-[13px]
            placeholder:text-ink-faint hover:border-line-strong focus:border-accent
            focus:outline-none"
        />
      </form>

      {classes.length === 0 && (
        <p className="px-3 pb-3 text-[12px] leading-relaxed text-ink-faint">
          Add at least one class before you can draw a box.
        </p>
      )}
    </div>
  );
}
