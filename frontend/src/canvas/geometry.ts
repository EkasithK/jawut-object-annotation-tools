import type { DraftBox } from "../api/labeling";

/**
 * Image-space to canvas-space transform.
 *
 * Three coordinate systems are in play and mixing them is the classic source of
 * canvas bugs, so they are named consistently everywhere:
 *
 *   normalized  0..1, relative to the image. What the API and database use.
 *   image       pixels within the source image. What zoom is expressed against.
 *   canvas      pixels on screen. What pointer events give and drawing consumes.
 */
export interface View {
  scale: number;
  ox: number;
  oy: number;
}

export interface Size {
  width: number;
  height: number;
}

export const IDENTITY_VIEW: View = { scale: 1, ox: 0, oy: 0 };

export const MIN_SCALE = 0.05;
export const MAX_SCALE = 40;

/** Scale and centre the image so all of it is visible with a small margin. */
export function fitView(image: Size, viewport: Size, padding = 24): View {
  if (image.width <= 0 || image.height <= 0) return IDENTITY_VIEW;

  const available = {
    width: Math.max(1, viewport.width - padding * 2),
    height: Math.max(1, viewport.height - padding * 2),
  };
  const scale = Math.min(
    available.width / image.width,
    available.height / image.height,
  );

  return {
    scale,
    ox: (viewport.width - image.width * scale) / 2,
    oy: (viewport.height - image.height * scale) / 2,
  };
}

export const toCanvas = (view: View, x: number, y: number): [number, number] => [
  x * view.scale + view.ox,
  y * view.scale + view.oy,
];

export const toImage = (view: View, x: number, y: number): [number, number] => [
  (x - view.ox) / view.scale,
  (y - view.oy) / view.scale,
];

/** Zoom about a fixed canvas point, so the pixel under the cursor stays put. */
export function zoomAt(
  view: View,
  canvasX: number,
  canvasY: number,
  factor: number,
): View {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
  const applied = scale / view.scale;
  return {
    scale,
    ox: canvasX - (canvasX - view.ox) * applied,
    oy: canvasY - (canvasY - view.oy) * applied,
  };
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Normalized centre form to a normalized top-left rectangle. */
export const boxToRect = (box: DraftBox): Rect => ({
  x: box.cx - box.w / 2,
  y: box.cy - box.h / 2,
  w: box.w,
  h: box.h,
});

/** Normalized top-left rectangle back to centre form, normalizing negatives. */
export function rectToBox(rect: Rect, classId: string, id?: string): DraftBox {
  const x = Math.min(rect.x, rect.x + rect.w);
  const y = Math.min(rect.y, rect.y + rect.h);
  const w = Math.abs(rect.w);
  const h = Math.abs(rect.h);
  return { ...(id ? { id } : {}), class_id: classId, cx: x + w / 2, cy: y + h / 2, w, h };
}

export const clamp01 = (value: number): number =>
  Math.min(1, Math.max(0, value));

/** Trim a rectangle to the image, matching what the server does on save. */
export function clampRect(rect: Rect): Rect {
  const left = clamp01(Math.min(rect.x, rect.x + rect.w));
  const top = clamp01(Math.min(rect.y, rect.y + rect.h));
  const right = clamp01(Math.max(rect.x, rect.x + rect.w));
  const bottom = clamp01(Math.max(rect.y, rect.y + rect.h));
  return { x: left, y: top, w: right - left, h: bottom - top };
}

export type HandleId =
  | "nw"
  | "n"
  | "ne"
  | "e"
  | "se"
  | "s"
  | "sw"
  | "w";

export const HANDLES: readonly HandleId[] = [
  "nw",
  "n",
  "ne",
  "e",
  "se",
  "s",
  "sw",
  "w",
];

/** Handle position in normalized space, as a fraction along each edge. */
export function handlePoint(rect: Rect, handle: HandleId): [number, number] {
  const midX = rect.x + rect.w / 2;
  const midY = rect.y + rect.h / 2;
  const right = rect.x + rect.w;
  const bottom = rect.y + rect.h;

  switch (handle) {
    case "nw":
      return [rect.x, rect.y];
    case "n":
      return [midX, rect.y];
    case "ne":
      return [right, rect.y];
    case "e":
      return [right, midY];
    case "se":
      return [right, bottom];
    case "s":
      return [midX, bottom];
    case "sw":
      return [rect.x, bottom];
    case "w":
      return [rect.x, midY];
  }
}

/** Apply a drag to one handle, moving only the edges that handle controls. */
export function resizeRect(
  rect: Rect,
  handle: HandleId,
  nx: number,
  ny: number,
): Rect {
  let { x, y } = rect;
  let right = rect.x + rect.w;
  let bottom = rect.y + rect.h;

  if (handle.includes("w")) x = nx;
  if (handle.includes("e")) right = nx;
  if (handle.includes("n")) y = ny;
  if (handle.includes("s")) bottom = ny;

  return clampRect({ x, y, w: right - x, h: bottom - y });
}

export const CURSOR_FOR_HANDLE: Record<HandleId, string> = {
  nw: "nwse-resize",
  n: "ns-resize",
  ne: "nesw-resize",
  e: "ew-resize",
  se: "nwse-resize",
  s: "ns-resize",
  sw: "nesw-resize",
  w: "ew-resize",
};

/**
 * Index of the topmost box under a point, or -1.
 *
 * Smallest-area-first so a small box drawn inside a large one stays reachable —
 * otherwise the enclosing box swallows every click.
 */
export function boxAtPoint(boxes: DraftBox[], nx: number, ny: number): number {
  let best = -1;
  let bestArea = Infinity;

  boxes.forEach((box, index) => {
    const rect = boxToRect(box);
    const inside =
      nx >= rect.x &&
      nx <= rect.x + rect.w &&
      ny >= rect.y &&
      ny <= rect.y + rect.h;
    const area = rect.w * rect.h;
    if (inside && area < bestArea) {
      best = index;
      bestArea = area;
    }
  });

  return best;
}
