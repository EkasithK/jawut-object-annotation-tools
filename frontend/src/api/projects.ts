import { z } from "zod";

import { api } from "./client";

export const projectSummarySchema = z.object({
  name: z.string(),
  path: z.string(),
  schema_version: z.number(),
  created_at: z.string(),
});

export const recentEntrySchema = z.object({
  name: z.string(),
  path: z.string(),
  opened_at: z.string(),
});

export const welcomeStateSchema = z.object({
  open_project: projectSummarySchema.nullable(),
  recent: z.array(recentEntrySchema),
  default_projects_dir: z.string(),
});

export const recentListSchema = z.object({
  recent: z.array(recentEntrySchema),
});

export type ProjectSummary = z.infer<typeof projectSummarySchema>;
export type RecentEntry = z.infer<typeof recentEntrySchema>;
export type WelcomeState = z.infer<typeof welcomeStateSchema>;

const BASE = "/api/v1/projects";

export const getWelcomeState = () => api.get(BASE, welcomeStateSchema);

export const createProject = (name: string, parentDir: string) =>
  api.post(BASE, projectSummarySchema, { name, parent_dir: parentDir });

export const openProject = (path: string) =>
  api.post(`${BASE}/open`, projectSummarySchema, { path });

export const closeProject = () =>
  api.post(`${BASE}/close`, welcomeStateSchema);

export const forgetProject = (path: string) =>
  api.post(`${BASE}/forget`, recentListSchema, { path });
