import { useEffect, useState } from "react";

import {
  createProject,
  forgetProject,
  getWelcomeState,
  openProject,
  type RecentEntry,
} from "../api/projects";
import { ApiError } from "../api/client";
import { Frame } from "../components/Frame";
import { OpenDatasetDialog } from "../components/OpenDatasetDialog";
import { PathField } from "../components/PathField";
import { useAppStore } from "../store";

function relativeDay(iso: string): string {
  const days = Math.floor((Date.now() - Date.parse(iso)) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

/** Trim a long path to its last two components, which is what identifies it. */
function shortPath(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.length <= 2 ? path : `…/${parts.slice(-2).join("/")}`;
}

export function Welcome() {
  const setProject = useAppStore((s) => s.setProject);

  const [name, setName] = useState("");
  const [parentDir, setParentDir] = useState("");
  const [openPath, setOpenPath] = useState("");
  const [datasetOpen, setDatasetOpen] = useState(false);
  const [recent, setRecent] = useState<RecentEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getWelcomeState()
      .then((state) => {
        setRecent(state.recent);
        setParentDir(state.default_projects_dir);
        if (state.open_project) setProject(state.open_project);
      })
      .catch((e: unknown) => setError(describe(e)));
  }, [setProject]);

  function describe(e: unknown): string {
    if (e instanceof ApiError) return e.message;
    return e instanceof Error ? e.message : String(e);
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      setProject(await createProject(name.trim(), parentDir.trim()));
    } catch (e: unknown) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleOpen(path: string) {
    setError(null);
    setBusy(true);
    try {
      setProject(await openProject(path));
    } catch (e: unknown) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleForget(path: string) {
    try {
      setRecent((await forgetProject(path)).recent);
    } catch (e: unknown) {
      setError(describe(e));
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-6 py-16">
      <div className="w-full max-w-lg">
        {/* The wordmark is drawn the way this tool draws a labeled object. */}
        <Frame label="jawut" active className="mb-14 px-7 py-8">
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight">
            Object Annotation Tools
          </h1>
          <p className="mt-1.5 text-ink-muted">
            Draw boxes, manage classes, export YOLO.
          </p>
        </Frame>

        <section className="mb-12">
          <SectionLabel>New project</SectionLabel>

          <form onSubmit={handleCreate} className="mt-4 space-y-3">
            <Field
              id="project-name"
              label="Name"
              value={name}
              onChange={setName}
              placeholder="Helmet relabel"
              autoFocus
            />
            <PathField
              id="project-location"
              label="Location"
              value={parentDir}
              onChange={setParentDir}
              size="md"
            />

            <button
              type="submit"
              disabled={busy || !name.trim() || !parentDir.trim()}
              className="mt-1 w-full bg-accent px-4 py-2.5 text-sm font-medium
                text-on-accent transition-colors hover:bg-accent-hover
                focus-visible:outline focus-visible:outline-2
                focus-visible:outline-offset-2 focus-visible:outline-accent
                disabled:cursor-not-allowed disabled:bg-surface-3
                disabled:text-ink-faint"
            >
              Create project
            </button>
          </form>

          <p className="mt-2.5 font-mono text-[12px] leading-relaxed text-ink-faint">
            Creates {parentDir || "…"}
            {parentDir && !parentDir.endsWith("/") ? "/" : ""}
            {name.trim() || "<name>"}
          </p>
        </section>

        {/* The route in for anyone who already has a labeled or half-labeled
            dataset, which is most people who arrive with work to finish. */}
        <section className="mb-12">
          <SectionLabel>Already have a dataset?</SectionLabel>

          <button
            onClick={() => setDatasetOpen(true)}
            className="mt-4 w-full border border-line-strong px-4 py-3 text-left
              transition-colors hover:border-accent
              focus-visible:outline focus-visible:outline-2
              focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <span className="block text-sm font-medium">
              Open existing dataset…
            </span>
            <span className="mt-0.5 block text-[12px] leading-relaxed text-ink-faint">
              Browse to a folder of images. Labels, class names and folder layout
              are detected for you.
            </span>
          </button>
        </section>

        {/* Without this, a project that is not in the recent list — a fresh
            machine, a cleared list, a folder someone was handed — cannot be
            reached at all. */}
        <section className="mb-12">
          <SectionLabel>Open a project</SectionLabel>

          <div className="mt-4">
            <PathField
              id="open-path"
              label="Project folder"
              value={openPath}
              onChange={setOpenPath}
              placeholder="C:\Users\you\Documents\jawut\Helmet relabel"
              size="md"
              hint="The folder holding project.db."
            />
          </div>

          <button
            onClick={() => void handleOpen(openPath.trim())}
            disabled={busy || !openPath.trim()}
            className="mt-3 w-full border border-line-strong px-4 py-2.5 text-sm
              transition-colors hover:border-accent hover:text-accent
              focus-visible:outline focus-visible:outline-2
              focus-visible:outline-offset-2 focus-visible:outline-accent
              disabled:cursor-not-allowed disabled:border-line
              disabled:text-ink-faint disabled:hover:text-ink-faint"
          >
            Open project
          </button>
        </section>

        {recent.length > 0 && (
          <section>
            <SectionLabel>Recent</SectionLabel>

            <ul className="mt-3 divide-y divide-line border-y border-line">
              {recent.map((entry) => (
                <li key={entry.path} className="group flex items-stretch">
                  <button
                    onClick={() => void handleOpen(entry.path)}
                    disabled={busy}
                    className="flex min-w-0 flex-1 items-baseline gap-3 py-3 pr-3
                      text-left transition-colors hover:bg-surface-1
                      focus-visible:outline focus-visible:outline-2
                      focus-visible:-outline-offset-2
                      focus-visible:outline-accent disabled:opacity-50"
                  >
                    <span className="shrink-0 truncate font-medium">
                      {entry.name}
                    </span>
                    <span
                      className="min-w-0 flex-1 truncate font-mono text-[12px]
                        text-ink-faint"
                      title={entry.path}
                    >
                      {shortPath(entry.path)}
                    </span>
                    <span className="shrink-0 font-mono text-[12px] text-ink-faint">
                      {relativeDay(entry.opened_at)}
                    </span>
                  </button>

                  <button
                    onClick={() => void handleForget(entry.path)}
                    aria-label={`Remove ${entry.name} from this list`}
                    title="Remove from this list"
                    className="px-3 text-ink-faint opacity-0 transition
                      hover:text-ink focus-visible:opacity-100
                      focus-visible:outline focus-visible:outline-2
                      focus-visible:-outline-offset-2
                      focus-visible:outline-accent group-hover:opacity-100"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {error && (
          <p
            role="alert"
            className="mt-8 border-l-2 border-status-review bg-surface-1 px-4 py-3
              text-[14px] text-ink"
          >
            {error}
          </p>
        )}
      </div>

      <OpenDatasetDialog
        open={datasetOpen}
        defaultParentDir={parentDir}
        onClose={() => setDatasetOpen(false)}
        onOpened={setProject}
      />
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2
      className="font-mono text-[12px] uppercase tracking-[0.18em] font-medium text-ink-faint"
    >
      {children}
    </h2>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
  autoFocus = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1.5 block text-[12px] uppercase tracking-wider font-medium text-ink-muted"
      >
        {label}
      </label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        spellCheck={false}
        className="w-full border border-line bg-surface-1 px-3 py-2.5 text-ink
          transition-colors placeholder:text-ink-faint hover:border-line-strong
          focus:border-accent focus:outline-none"
      />
    </div>
  );
}
