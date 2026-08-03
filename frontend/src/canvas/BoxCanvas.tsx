import { useCallback, useEffect, useRef, useState } from "react";

import type { DraftBox, ObjectClass } from "../api/labeling";
import {
  boxAtPoint,
  boxToRect,
  clampRect,
  CURSOR_FOR_HANDLE,
  fitView,
  HANDLES,
  handlePoint,
  type HandleId,
  IDENTITY_VIEW,
  rectToBox,
  resizeRect,
  toCanvas,
  toImage,
  type View,
  zoomAt,
} from "./geometry";

const HANDLE_SIZE = 8;
const HANDLE_HIT_RADIUS = 7;
/** Below this, a drag was a click that happened to wobble, not a new box. */
const MIN_DRAW_PIXELS = 4;

type Drag =
  | { kind: "none" }
  | { kind: "pan"; startX: number; startY: number; view: View }
  | { kind: "draw"; anchorX: number; anchorY: number }
  | { kind: "move"; index: number; grabX: number; grabY: number }
  | { kind: "resize"; index: number; handle: HandleId };

export interface BoxCanvasProps {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  boxes: DraftBox[];
  classes: ObjectClass[];
  selectedIndex: number;
  activeClassId: string | null;
  drawMode: boolean;
  onBoxesChange: (boxes: DraftBox[], committed: boolean) => void;
  onSelect: (index: number) => void;
  onDrawModeEnd: () => void;
  fitToken: number;
}

export function BoxCanvas({
  imageUrl,
  imageWidth,
  imageHeight,
  boxes,
  classes,
  selectedIndex,
  activeClassId,
  drawMode,
  onBoxesChange,
  onSelect,
  onDrawModeEnd,
  fitToken,
}: BoxCanvasProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);

  const [view, setView] = useState<View>(IDENTITY_VIEW);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [drag, setDrag] = useState<Drag>({ kind: "none" });
  const [pending, setPending] = useState<DraftBox | null>(null);
  const [hoverHandle, setHoverHandle] = useState<HandleId | null>(null);
  const [ready, setReady] = useState(false);

  const colorFor = useCallback(
    (classId: string) =>
      classes.find((c) => c.id === classId)?.color ?? "#8a94a6",
    [classes],
  );

  // Track the viewport so fitting and hit-testing stay correct through resizes.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setViewport({ width, height });
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setReady(false);
    const image = new Image();
    image.src = imageUrl;
    image.onload = () => {
      imageRef.current = image;
      setReady(true);
    };
    image.onerror = () => {
      imageRef.current = null;
      setReady(false);
    };
    return () => {
      image.onload = null;
      image.onerror = null;
    };
  }, [imageUrl]);

  // Refit on a new image, a resize, or an explicit request (the F key).
  useEffect(() => {
    if (viewport.width === 0 || imageWidth === 0) return;
    setView(fitView({ width: imageWidth, height: imageHeight }, viewport));
  }, [imageWidth, imageHeight, viewport, fitToken]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || viewport.width === 0) return;

    const context = canvas.getContext("2d");
    if (!context) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(viewport.width * dpr);
    canvas.height = Math.round(viewport.height * dpr);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, viewport.width, viewport.height);

    const image = imageRef.current;
    if (image && ready) {
      // Nearest-neighbour past 2x: labelers zoom in to find a boundary exactly,
      // and smoothing hides where one pixel ends and the next begins.
      context.imageSmoothingEnabled = view.scale < 2;
      const [x, y] = toCanvas(view, 0, 0);
      context.drawImage(
        image,
        x,
        y,
        imageWidth * view.scale,
        imageHeight * view.scale,
      );
    }

    const paint = (box: DraftBox, index: number, ghost: boolean) => {
      const rect = boxToRect(box);
      const [x1, y1] = toCanvas(view, rect.x * imageWidth, rect.y * imageHeight);
      const width = rect.w * imageWidth * view.scale;
      const height = rect.h * imageHeight * view.scale;
      const selected = index === selectedIndex;
      const color = colorFor(box.class_id);

      context.save();
      if (ghost) context.setLineDash([5, 4]);
      context.strokeStyle = color;
      context.lineWidth = selected ? 2.5 : 1.5;
      context.strokeRect(x1, y1, width, height);

      // A translucent wash makes overlapping boxes readable without hiding the
      // image underneath, which is the whole point of the tool.
      context.globalAlpha = selected ? 0.18 : 0.1;
      context.fillStyle = color;
      context.fillRect(x1, y1, width, height);
      context.restore();

      if (!ghost) {
        const label = classes.find((c) => c.id === box.class_id)?.name ?? "?";
        context.save();
        context.font =
          "500 11px ui-sans-serif, system-ui, -apple-system, sans-serif";
        const textWidth = context.measureText(label).width;
        context.fillStyle = color;
        context.fillRect(x1, y1 - 15, textWidth + 10, 15);
        context.fillStyle = "#0e1013";
        context.fillText(label, x1 + 5, y1 - 4);
        context.restore();
      }

      if (selected && !ghost) {
        context.save();
        context.fillStyle = "#ffffff";
        context.strokeStyle = color;
        context.lineWidth = 1.5;
        for (const handle of HANDLES) {
          const [hx, hy] = handlePoint(rect, handle);
          const [px, py] = toCanvas(view, hx * imageWidth, hy * imageHeight);
          context.fillRect(
            px - HANDLE_SIZE / 2,
            py - HANDLE_SIZE / 2,
            HANDLE_SIZE,
            HANDLE_SIZE,
          );
          context.strokeRect(
            px - HANDLE_SIZE / 2,
            py - HANDLE_SIZE / 2,
            HANDLE_SIZE,
            HANDLE_SIZE,
          );
        }
        context.restore();
      }
    };

    boxes.forEach((box, index) => paint(box, index, false));
    if (pending) paint(pending, -1, true);
  }, [
    boxes,
    classes,
    colorFor,
    imageHeight,
    imageWidth,
    pending,
    ready,
    selectedIndex,
    view,
    viewport,
  ]);

  useEffect(() => {
    draw();
  }, [draw]);

  /** Canvas-space position of any event that carries client coordinates. */
  const pointer = useCallback((event: { clientX: number; clientY: number }) => {
    const canvas = canvasRef.current;
    if (!canvas) return { canvasX: 0, canvasY: 0 };
    const bounds = canvas.getBoundingClientRect();
    return {
      canvasX: event.clientX - bounds.left,
      canvasY: event.clientY - bounds.top,
    };
  }, []);

  const toNormalized = useCallback(
    (canvasX: number, canvasY: number): [number, number] => {
      const [ix, iy] = toImage(view, canvasX, canvasY);
      return [ix / imageWidth, iy / imageHeight];
    },
    [imageHeight, imageWidth, view],
  );

  const handleUnder = useCallback(
    (canvasX: number, canvasY: number): HandleId | null => {
      const box = boxes[selectedIndex];
      if (!box) return null;
      const rect = boxToRect(box);
      for (const handle of HANDLES) {
        const [hx, hy] = handlePoint(rect, handle);
        const [px, py] = toCanvas(view, hx * imageWidth, hy * imageHeight);
        if (
          Math.abs(px - canvasX) <= HANDLE_HIT_RADIUS &&
          Math.abs(py - canvasY) <= HANDLE_HIT_RADIUS
        ) {
          return handle;
        }
      }
      return null;
    },
    [boxes, imageHeight, imageWidth, selectedIndex, view],
  );

  function onPointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    const { canvasX, canvasY } = pointer(event);
    canvasRef.current?.setPointerCapture(event.pointerId);

    // Middle button or space-less right-drag pans; the left button labels.
    if (event.button === 1 || event.button === 2) {
      setDrag({ kind: "pan", startX: canvasX, startY: canvasY, view });
      return;
    }

    const [nx, ny] = toNormalized(canvasX, canvasY);

    if (drawMode && activeClassId) {
      setDrag({ kind: "draw", anchorX: nx, anchorY: ny });
      setPending({ class_id: activeClassId, cx: nx, cy: ny, w: 0, h: 0 });
      return;
    }

    const handle = handleUnder(canvasX, canvasY);
    if (handle) {
      setDrag({ kind: "resize", index: selectedIndex, handle });
      return;
    }

    const hit = boxAtPoint(boxes, nx, ny);
    if (hit >= 0) {
      onSelect(hit);
      const rect = boxToRect(boxes[hit]!);
      setDrag({ kind: "move", index: hit, grabX: nx - rect.x, grabY: ny - rect.y });
      return;
    }

    onSelect(-1);
    setDrag({ kind: "pan", startX: canvasX, startY: canvasY, view });
  }

  function onPointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    const { canvasX, canvasY } = pointer(event);

    if (drag.kind === "none") {
      setHoverHandle(handleUnder(canvasX, canvasY));
      return;
    }

    const [nx, ny] = toNormalized(canvasX, canvasY);

    switch (drag.kind) {
      case "pan":
        setView({
          scale: drag.view.scale,
          ox: drag.view.ox + (canvasX - drag.startX),
          oy: drag.view.oy + (canvasY - drag.startY),
        });
        break;

      case "draw": {
        const rect = clampRect({
          x: drag.anchorX,
          y: drag.anchorY,
          w: nx - drag.anchorX,
          h: ny - drag.anchorY,
        });
        setPending(rectToBox(rect, activeClassId ?? ""));
        break;
      }

      case "move": {
        const box = boxes[drag.index];
        if (!box) break;
        const rect = boxToRect(box);
        // Shift the whole box, then stop it at the frame rather than letting it
        // shrink — a drag should never silently resize what it is moving.
        const width = rect.w;
        const height = rect.h;
        const x = Math.min(1 - width, Math.max(0, nx - drag.grabX));
        const y = Math.min(1 - height, Math.max(0, ny - drag.grabY));
        const next = [...boxes];
        next[drag.index] = rectToBox(
          { x, y, w: width, h: height },
          box.class_id,
          box.id,
        );
        onBoxesChange(next, false);
        break;
      }

      case "resize": {
        const box = boxes[drag.index];
        if (!box) break;
        const resized = resizeRect(boxToRect(box), drag.handle, nx, ny);
        const next = [...boxes];
        next[drag.index] = rectToBox(resized, box.class_id, box.id);
        onBoxesChange(next, false);
        break;
      }
    }
  }

  function onPointerUp(event: React.PointerEvent<HTMLCanvasElement>) {
    canvasRef.current?.releasePointerCapture(event.pointerId);

    if (drag.kind === "draw" && pending && activeClassId) {
      const wideEnough = pending.w * imageWidth * view.scale >= MIN_DRAW_PIXELS;
      const tallEnough = pending.h * imageHeight * view.scale >= MIN_DRAW_PIXELS;
      if (wideEnough && tallEnough) {
        const next = [...boxes, pending];
        onBoxesChange(next, true);
        onSelect(next.length - 1);
      }
      setPending(null);
      onDrawModeEnd();
    } else if (drag.kind === "move" || drag.kind === "resize") {
      onBoxesChange(boxes, true);
    }

    setDrag({ kind: "none" });
  }

  function onWheel(event: React.WheelEvent<HTMLCanvasElement>) {
    const { canvasX, canvasY } = pointer(event);
    setView(zoomAt(view, canvasX, canvasY, event.deltaY < 0 ? 1.12 : 1 / 1.12));
  }

  const cursor = drawMode
    ? "crosshair"
    : drag.kind === "pan"
      ? "grabbing"
      : hoverHandle
        ? CURSOR_FOR_HANDLE[hoverHandle]
        : "default";

  return (
    <div ref={hostRef} className="no-select relative h-full w-full overflow-hidden">
      <canvas
        ref={canvasRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onWheel={onWheel}
        onContextMenu={(e) => e.preventDefault()}
        style={{ cursor }}
        className="absolute inset-0 touch-none"
      />

      {!ready && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <span className="font-mono text-[11px] text-ink-faint">
            loading image…
          </span>
        </div>
      )}

      <div
        className="pointer-events-none absolute bottom-3 right-3 font-mono
          text-[10px] text-ink-faint"
      >
        {Math.round(view.scale * 100)}%
      </div>
    </div>
  );
}
