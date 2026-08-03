import { closeProject } from "./api/projects";
import { Welcome } from "./screens/Welcome";
import { useAppStore } from "./store";

export function App() {
  const project = useAppStore((s) => s.project);
  const setProject = useAppStore((s) => s.setProject);

  if (!project) {
    return <Welcome />;
  }

  return (
    <div className="flex h-full flex-col">
      <header
        className="flex shrink-0 items-baseline gap-3 border-b border-line
          px-4 py-2.5"
      >
        <span className="font-medium">{project.name}</span>
        <span
          className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-faint"
          title={project.path}
        >
          {project.path}
        </span>
        <button
          onClick={() => {
            void closeProject().then(() => setProject(null));
          }}
          className="text-[12px] text-ink-muted transition-colors hover:text-ink
            focus-visible:outline focus-visible:outline-2
            focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Close project
        </button>
      </header>

      <main className="flex flex-1 items-center justify-center px-6">
        <p className="text-ink-faint">
          Add images to start labeling.
        </p>
      </main>
    </div>
  );
}
