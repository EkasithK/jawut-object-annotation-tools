import { z } from "zod";

import { api } from "./client";

export const IMAGE_STATUSES = [
  "unlabeled",
  "in_progress",
  "done",
  "needs_review",
] as const;

export type ImageStatus = (typeof IMAGE_STATUSES)[number];

export const objectClassSchema = z.object({
  id: z.string(),
  name: z.string(),
  color: z.string(),
  order_index: z.number(),
});

export const classListSchema = z.object({
  classes: z.array(objectClassSchema),
});

export const classUsageSchema = z.object({
  class_id: z.string(),
  name: z.string(),
  annotations: z.number(),
  images: z.number(),
});

export const deleteResultSchema = z.object({
  deleted: classUsageSchema,
  reassigned_to: z.string().nullable(),
  classes: z.array(objectClassSchema),
});

export const imageRecordSchema = z.object({
  id: z.string(),
  filename: z.string(),
  width: z.number(),
  height: z.number(),
  status: z.enum(IMAGE_STATUSES),
  annotation_count: z.number(),
});

export const statusCountsSchema = z.object({
  unlabeled: z.number(),
  in_progress: z.number(),
  done: z.number(),
  needs_review: z.number(),
  total: z.number(),
});

export const imageListSchema = z.object({
  images: z.array(imageRecordSchema),
  counts: statusCountsSchema,
});

export const storedBoxSchema = z.object({
  id: z.string(),
  class_id: z.string(),
  cx: z.number(),
  cy: z.number(),
  w: z.number(),
  h: z.number(),
});

export const imageDetailSchema = z.object({
  image: imageRecordSchema,
  boxes: z.array(storedBoxSchema),
  previous_id: z.string().nullable(),
  next_id: z.string().nullable(),
});

export const saveResultSchema = z.object({
  boxes: z.array(storedBoxSchema),
  image: imageRecordSchema,
});

export const importResultSchema = z.object({
  imported: z.number(),
  duplicates: z.number(),
  skipped: z.array(z.object({ path: z.string(), reason: z.string() })),
});

export const reassignResultSchema = z.object({ moved: z.number() });

export type ObjectClass = z.infer<typeof objectClassSchema>;
export type ClassUsage = z.infer<typeof classUsageSchema>;
export type ImageRecord = z.infer<typeof imageRecordSchema>;
export type StatusCounts = z.infer<typeof statusCountsSchema>;
export type StoredBox = z.infer<typeof storedBoxSchema>;
export type ImageDetail = z.infer<typeof imageDetailSchema>;
export type ImportResult = z.infer<typeof importResultSchema>;

/** A box being edited on the canvas. New boxes have no id until saved. */
export interface DraftBox {
  id?: string;
  class_id: string;
  cx: number;
  cy: number;
  w: number;
  h: number;
}

export const listClasses = () => api.get("/api/v1/classes", classListSchema);

export const createClass = (name: string, color?: string) =>
  api.post("/api/v1/classes", objectClassSchema, { name, color });

export const updateClass = (
  id: string,
  patch: { name?: string; color?: string },
) => api.patch(`/api/v1/classes/${id}`, objectClassSchema, patch);

export const reorderClasses = (orderedIds: string[]) =>
  api.post("/api/v1/classes/reorder", classListSchema, {
    ordered_ids: orderedIds,
  });

export const classUsage = (id: string) =>
  api.get(`/api/v1/classes/${id}/usage`, classUsageSchema);

export const deleteClass = (id: string, reassignTo: string | null) =>
  api.post(`/api/v1/classes/${id}/delete`, deleteResultSchema, {
    reassign_to: reassignTo,
  });

export const importImages = (
  source: string,
  options: { recursive?: boolean; copyIntoProject?: boolean } = {},
) =>
  api.post("/api/v1/images/import", importResultSchema, {
    source,
    recursive: options.recursive ?? true,
    copy_into_project: options.copyIntoProject ?? true,
  });

export const listImages = (status?: ImageStatus) => {
  const query = status ? `?status=${status}` : "";
  return api.get(`/api/v1/images${query}`, imageListSchema);
};

export const getImage = (id: string, status?: ImageStatus) => {
  const query = status ? `?status=${status}` : "";
  return api.get(`/api/v1/images/${id}${query}`, imageDetailSchema);
};

export const imageFileUrl = (id: string) => `/api/v1/images/${id}/file`;

export const setImageStatus = (id: string, status: ImageStatus) =>
  api.patch(`/api/v1/images/${id}/status`, imageRecordSchema, { status });

export const saveBoxes = (
  imageId: string,
  boxes: DraftBox[],
  status?: ImageStatus,
) =>
  api.put(`/api/v1/annotations/${imageId}`, saveResultSchema, {
    boxes,
    status: status ?? null,
  });

export const reassignAllBoxes = (fromClass: string, toClass: string) =>
  api.post("/api/v1/annotations/reassign", reassignResultSchema, {
    from_class: fromClass,
    to_class: toClass,
  });
