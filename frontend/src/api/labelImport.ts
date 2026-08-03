import { z } from "zod";

import { api } from "./client";

export const ISSUE_KINDS = [
  "malformed",
  "unknown_class",
  "out_of_range",
  "degenerate",
  "unmatched_label",
  "keypoints_dropped",
  "pixels_normalized",
  "coords_clamped",
] as const;

export type IssueKind = (typeof ISSUE_KINDS)[number];

/** Kinds that describe a repair the importer made, not a rejection. */
export const REPAIR_KINDS: ReadonlySet<IssueKind> = new Set([
  "keypoints_dropped",
  "pixels_normalized",
  "coords_clamped",
]);

export const importIssueSchema = z.object({
  file: z.string(),
  line: z.number().nullable(),
  kind: z.enum(ISSUE_KINDS),
  detail: z.string(),
});

export const labelPreviewSchema = z.object({
  label_files: z.number(),
  matched_images: z.number(),
  unmatched_labels: z.array(z.string()),
  images_without_labels: z.number(),
  source_classes: z.object({
    names: z.array(z.string()),
    from_data_yaml: z.boolean(),
    data_yaml_path: z.string().nullable(),
  }),
  box_counts: z.record(z.number()),
  issues: z.array(importIssueSchema),
});

export const labelImportResultSchema = z.object({
  images_labeled: z.number(),
  boxes_created: z.number(),
  images_marked_empty: z.number(),
  skipped_boxes: z.number(),
  issues: z.array(importIssueSchema),
});

export type ImportIssue = z.infer<typeof importIssueSchema>;
export type LabelPreview = z.infer<typeof labelPreviewSchema>;
export type LabelImportResult = z.infer<typeof labelImportResultSchema>;

export const previewLabels = (labelsDir: string) =>
  api.post("/api/v1/labels/preview", labelPreviewSchema, {
    labels_dir: labelsDir,
  });

export const applyLabels = (
  labelsDir: string,
  classMapping: Record<string, string | null>,
  overwrite: boolean,
) =>
  api.post("/api/v1/labels/import", labelImportResultSchema, {
    labels_dir: labelsDir,
    class_mapping: classMapping,
    overwrite,
  });
