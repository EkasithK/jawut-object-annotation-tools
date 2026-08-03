import { create } from "zustand";

import type { ProjectSummary } from "./api/projects";

interface AppState {
  project: ProjectSummary | null;
  setProject: (project: ProjectSummary | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  project: null,
  setProject: (project) => set({ project }),
}));
