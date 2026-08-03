import { z } from "zod";

import { api } from "./client";
import { importIssueSchema } from "./labelImport";
import { projectSummarySchema } from "./projects";

export const datasetScanSchema = z.object({
  root: z.string(),
  layout: z.enum(["split", "images_labels", "flat", "images_only", "empty"]),
  image_dirs: z.array(z.string()),
  label_dirs: z.array(z.string()),
  image_count: z.number(),
  label_count: z.number(),
  data_yaml: z.string().nullable(),
  class_names: z.array(z.string()),
  summary: z.string(),
});

export const adoptResultSchema = z.object({
  project: projectSummarySchema,
  images_imported: z.number(),
  images_skipped: z.number(),
  classes_created: z.number(),
  boxes_created: z.number(),
  images_labeled: z.number(),
  images_marked_empty: z.number(),
  issues: z.array(importIssueSchema),
});

export type DatasetScan = z.infer<typeof datasetScanSchema>;
export type AdoptResult = z.infer<typeof adoptResultSchema>;

/** How each recognised folder shape is described to someone non-technical. */
export const LAYOUT_LABELS: Record<DatasetScan["layout"], string> = {
  split: "train / valid / test folders",
  images_labels: "images and labels folders",
  flat: "images and labels together in one folder",
  images_only: "images, not labeled yet",
  empty: "nothing recognisable",
};

export const scanDataset = (path: string) =>
  api.post("/api/v1/datasets/scan", datasetScanSchema, { path });

export const adoptDataset = (
  path: string,
  name: string,
  parentDir: string,
  copyImages: boolean,
) =>
  api.post("/api/v1/datasets/adopt", adoptResultSchema, {
    path,
    name,
    parent_dir: parentDir,
    copy_images: copyImages,
  });
