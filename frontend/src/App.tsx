import { Welcome } from "./screens/Welcome";
import { Workspace } from "./screens/Workspace";
import { useAppStore } from "./store";

export function App() {
  const project = useAppStore((s) => s.project);
  return project ? <Workspace /> : <Welcome />;
}
