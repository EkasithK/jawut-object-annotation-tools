import { z } from "zod";

import { api } from "./client";

export const EXPORT_LAYOUTS = ["split", "flat"] as const;
export type ExportLayout = (typeof EXPORT_LAYOUTS)[number];

export const exportResultSchema = z.object({
  destination: z.string(),
  layout: z.enum(EXPORT_LAYOUTS),
  class_names: z.array(z.string()),
  images_exported: z.number(),
  boxes_exported: z.number(),
  empty_labels: z.number(),
  counts_per_split: z.record(z.number()),
  data_yaml: z.string(),
  manifest: z.string(),
});

export type ExportResult = z.infer<typeof exportResultSchema>;

export interface ExportRequest {
  destination: string;
  layout: ExportLayout;
  ratios: { train: number; val: number; test: number };
  seed: number;
  includeUnlabeled: boolean;
}

export const runExport = (request: ExportRequest) =>
  api.post("/api/v1/export", exportResultSchema, {
    destination: request.destination,
    layout: request.layout,
    ratios: request.ratios,
    seed: request.seed,
    include_unlabeled: request.includeUnlabeled,
  });
