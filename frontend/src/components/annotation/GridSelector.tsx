import { useRef, useEffect, useState, useCallback } from "react";
import { AlertTriangle } from "lucide-react";
import type { GridCoordinates } from "@/types";
import { loadImage } from "@/utils/imageUtils";

interface GridSelectorProps {
  imageUrl: string;
  onGridSelect: (coords: GridCoordinates) => void;
  initialCoords?: GridCoordinates | undefined;
  disabled?: boolean | undefined;
  // Screenshot info
  imageType?: string | undefined;
  extractedTitle?: string | null | undefined;
  onTitleChange?: ((title: string) => void) | undefined;
}

type DragMode =
  | "none"
  | "upper_left"
  | "upper_right"
  | "lower_left"
  | "lower_right"
  | "move"
  | "creating";

export const GridSelector = ({
  imageUrl,
  onGridSelect,
  initialCoords,
  disabled = false,
  imageType,
  extractedTitle,
  onTitleChange,
}: GridSelectorProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [upperLeft, setUpperLeft] = useState<{ x: number; y: number } | null>(
    initialCoords?.upper_left || null
  );
  const [lowerRight, setLowerRight] = useState<{ x: number; y: number } | null>(
    initialCoords?.lower_right || null
  );
  const [scale, setScale] = useState(1);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [cropOffset, setCropOffset] = useState(0);
  const [dragMode, setDragMode] = useState<DragMode>("none");
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(
    null,
  );
  const previousImageUrl = useRef<string>("");
  const onGridSelectRef = useRef(onGridSelect);

  // Keep ref up to date
  useEffect(() => {
    onGridSelectRef.current = onGridSelect;
  }, [onGridSelect]);

  // Handle initialCoords changes (when new screenshot is loaded)
  useEffect(() => {
    // Sync props to state when initialCoords changes (intentional pattern)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (initialCoords?.upper_left) setUpperLeft(initialCoords.upper_left);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (initialCoords?.lower_right) setLowerRight(initialCoords.lower_right);
  }, [initialCoords]);

  // Helper functions for canvas drawing (defined before redrawCanvas)
  const drawGrid = useCallback(
    (ctx: CanvasRenderingContext2D, width: number, height: number) => {
      ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
      ctx.lineWidth = 1;
      for (let i = 1; i < 24; i++) {
        const x = (width / 24) * i;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
    },
    []
  );

  const drawHandle = useCallback(
    (
      ctx: CanvasRenderingContext2D,
      x: number,
      y: number,
      size: number,
      color: string
    ) => {
      ctx.fillStyle = color;
      ctx.fillRect(x - size / 2, y - size / 2, size, size);
      ctx.strokeStyle = "white";
      ctx.lineWidth = 1;
      ctx.strokeRect(x - size / 2, y - size / 2, size, size);
    },
    []
  );

  const redrawCanvas = useCallback(
    (
      img: HTMLImageElement,
      ul: { x: number; y: number } | null,
      lr: { x: number; y: number } | null
    ) => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;

      const containerWidth = container.clientWidth || 800;
      // Crop to top 50% of the image
      const sourceHeight = img.naturalHeight / 2;
      const cropY = 0;

      const imageScale = containerWidth / img.naturalWidth;
      const displayHeight = sourceHeight * imageScale;

      canvas.width = containerWidth;
      canvas.height = displayHeight;
      setScale(imageScale);
      setCropOffset(cropY);

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.drawImage(
        img,
        0,
        cropY,
        img.naturalWidth,
        sourceHeight,
        0,
        0,
        containerWidth,
        displayHeight
      );
      drawGrid(ctx, containerWidth, displayHeight);

      if (ul && lr) {
        const scaledUL = {
          x: ul.x * imageScale,
          y: (ul.y - cropY) * imageScale,
        };
        const scaledLR = {
          x: lr.x * imageScale,
          y: (lr.y - cropY) * imageScale,
        };

        // Selection fill
        ctx.fillStyle = "rgba(59, 130, 246, 0.1)";
        ctx.fillRect(
          scaledUL.x,
          scaledUL.y,
          scaledLR.x - scaledUL.x,
          scaledLR.y - scaledUL.y
        );

        // Selection border
        ctx.strokeStyle = "#2563EB";
        ctx.lineWidth = 2;
        ctx.strokeRect(
          scaledUL.x,
          scaledUL.y,
          scaledLR.x - scaledUL.x,
          scaledLR.y - scaledUL.y
        );

        // Corner handles
        const handleSize = 6;
        drawHandle(ctx, scaledUL.x, scaledUL.y, handleSize, "#10B981");
        drawHandle(ctx, scaledLR.x, scaledUL.y, handleSize, "#F59E0B");
        drawHandle(ctx, scaledUL.x, scaledLR.y, handleSize, "#F59E0B");
        drawHandle(ctx, scaledLR.x, scaledLR.y, handleSize, "#EF4444");
      }
    },
    [drawGrid, drawHandle]
  );

  useEffect(() => {
    if (!imageUrl) return;
    const loadAndDrawImage = async () => {
      try {
        const img = await loadImage(imageUrl);
        setImage(img);
        previousImageUrl.current = imageUrl;
        redrawCanvas(img, upperLeft, lowerRight);
      } catch (error) {
        console.error("Failed to load image:", error);
      }
    };
    loadAndDrawImage();
  }, [imageUrl, redrawCanvas, upperLeft, lowerRight]);

  // Redraw when state changes (redrawCanvas updates scale/cropOffset internally)
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => {
    if (image) {
      redrawCanvas(image, upperLeft, lowerRight);
    }
  }, [upperLeft, lowerRight, image, redrawCanvas]);

  const getMousePos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / scale;
    const y = (e.clientY - rect.top) / scale + cropOffset;
    return { x: Math.round(x), y: Math.round(y) };
  };

  const hitTest = (pos: { x: number; y: number }): DragMode => {
    if (!upperLeft || !lowerRight) return "none";

    const threshold = 10 / scale;
    const ul = upperLeft;
    const lr = lowerRight;

    // Check corners first
    if (
      Math.abs(pos.x - ul.x) < threshold &&
      Math.abs(pos.y - ul.y) < threshold
    )
      return "upper_left";
    if (
      Math.abs(pos.x - lr.x) < threshold &&
      Math.abs(pos.y - ul.y) < threshold
    )
      return "upper_right";
    if (
      Math.abs(pos.x - ul.x) < threshold &&
      Math.abs(pos.y - lr.y) < threshold
    )
      return "lower_left";
    if (
      Math.abs(pos.x - lr.x) < threshold &&
      Math.abs(pos.y - lr.y) < threshold
    )
      return "lower_right";

    // Check if inside selection
    if (pos.x >= ul.x && pos.x <= lr.x && pos.y >= ul.y && pos.y <= lr.y)
      return "move";

    return "none";
  };

  const getCursor = (mode: DragMode): string => {
    switch (mode) {
      case "upper_left":
      case "lower_right":
        return "nwse-resize";
      case "upper_right":
      case "lower_left":
        return "nesw-resize";
      case "move":
        return "move";
      default:
        return "crosshair";
    }
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (disabled) return;

    const pos = getMousePos(e);
    if (!pos) return;

    const mode = hitTest(pos);

    if (mode !== "none") {
      setDragMode(mode);
      setDragStart(pos);
    } else {
      // Clicked outside - start new selection
      setUpperLeft(pos);
      setLowerRight(pos);
      setDragMode("creating");
      setDragStart(pos);
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const pos = getMousePos(e);
    if (!pos) return;

    // Update cursor
    const canvas = canvasRef.current;
    if (canvas) {
      if (disabled) {
        canvas.style.cursor = "not-allowed";
      } else if (dragMode !== "none") {
        canvas.style.cursor = getCursor(dragMode);
      } else {
        canvas.style.cursor = getCursor(hitTest(pos));
      }
    }

    if (disabled || dragMode === "none" || !dragStart) return;

    if (dragMode === "creating") {
      setLowerRight(pos);
    } else if (dragMode === "move" && upperLeft && lowerRight) {
      const dx = pos.x - dragStart.x;
      const dy = pos.y - dragStart.y;
      setUpperLeft({ x: upperLeft.x + dx, y: upperLeft.y + dy });
      setLowerRight({ x: lowerRight.x + dx, y: lowerRight.y + dy });
      setDragStart(pos);
    } else if (upperLeft && lowerRight) {
      // Resize handles
      let newUL = { ...upperLeft };
      let newLR = { ...lowerRight };

      switch (dragMode) {
        case "upper_left":
          newUL = pos;
          break;
        case "upper_right":
          newUL.y = pos.y;
          newLR.x = pos.x;
          break;
        case "lower_left":
          newUL.x = pos.x;
          newLR.y = pos.y;
          break;
        case "lower_right":
          newLR = pos;
          break;
      }

      // Ensure upper_left is always upper-left
      const finalUL = {
        x: Math.min(newUL.x, newLR.x),
        y: Math.min(newUL.y, newLR.y),
      };
      const finalLR = {
        x: Math.max(newUL.x, newLR.x),
        y: Math.max(newUL.y, newLR.y),
      };

      setUpperLeft(finalUL);
      setLowerRight(finalLR);
    }
  };

  const handleMouseUp = useCallback(() => {
    if (dragMode !== "none" && upperLeft && lowerRight) {
      // Normalize coordinates
      const finalUL = {
        x: Math.min(upperLeft.x, lowerRight.x),
        y: Math.min(upperLeft.y, lowerRight.y),
      };
      const finalLR = {
        x: Math.max(upperLeft.x, lowerRight.x),
        y: Math.max(upperLeft.y, lowerRight.y),
      };

      // Only save if selection has some size
      if (finalLR.x - finalUL.x > 5 && finalLR.y - finalUL.y > 5) {
        setUpperLeft(finalUL);
        setLowerRight(finalLR);
        const coords = { upper_left: finalUL, lower_right: finalLR };
        onGridSelectRef.current(coords);
      } else {
        // Too small, reset
        setUpperLeft(null);
        setLowerRight(null);
      }
    }
    setDragMode("none");
    setDragStart(null);
  }, [dragMode, upperLeft, lowerRight]);

  // Global mouse up handler for drag operations
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      if (dragMode !== "none") {
        handleMouseUp();
      }
    };

    window.addEventListener("mouseup", handleGlobalMouseUp);
    return () => window.removeEventListener("mouseup", handleGlobalMouseUp);
  }, [dragMode, handleMouseUp]);

  const moveSelection = useCallback(
    (dx: number, dy: number) => {
      if (!upperLeft || !lowerRight) return;

      const newUL = { x: upperLeft.x + dx, y: upperLeft.y + dy };
      const newLR = { x: lowerRight.x + dx, y: lowerRight.y + dy };

      setUpperLeft(newUL);
      setLowerRight(newLR);
      const coords = { upper_left: newUL, lower_right: newLR };
      onGridSelectRef.current(coords);
    },
    [upperLeft, lowerRight],
  );

  const resizeSelection = useCallback(
    (dw: number, dh: number) => {
      if (!upperLeft || !lowerRight) return;

      const newLR = {
        x: Math.max(upperLeft.x + 10, lowerRight.x + dw),
        y: Math.max(upperLeft.y + 10, lowerRight.y + dh),
      };

      setLowerRight(newLR);
      const coords = { upper_left: upperLeft, lower_right: newLR };
      onGridSelectRef.current(coords);
    },
    [upperLeft, lowerRight],
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // WASD works whenever there's a grid
      if (disabled || !upperLeft || !lowerRight) return;

      // Skip if typing in an input
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;

      const step = e.shiftKey ? 10 : 1;
      const key = e.key.toLowerCase();

      switch (key) {
        case "w":
          e.preventDefault();
          e.stopPropagation();
          if (e.ctrlKey || e.metaKey) {
            resizeSelection(0, -step);
          } else {
            moveSelection(0, -step);
          }
          break;
        case "s":
          e.preventDefault();
          e.stopPropagation();
          if (e.ctrlKey || e.metaKey) {
            resizeSelection(0, step);
          } else {
            moveSelection(0, step);
          }
          break;
        case "a":
          e.preventDefault();
          e.stopPropagation();
          if (e.ctrlKey || e.metaKey) {
            resizeSelection(-step, 0);
          } else {
            moveSelection(-step, 0);
          }
          break;
        case "d":
          e.preventDefault();
          e.stopPropagation();
          if (e.ctrlKey || e.metaKey) {
            resizeSelection(step, 0);
          } else {
            moveSelection(step, 0);
          }
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [disabled, upperLeft, lowerRight, moveSelection, resizeSelection]);

  const handleReset = () => {
    setUpperLeft(null);
    setLowerRight(null);
    setDragMode("none");
    if (image) {
      redrawCanvas(image, null, null);
    }
  };

  const hasSelection = upperLeft && lowerRight;

  return (
    <div className="space-y-2" ref={containerRef} data-testid="grid-selector">
      {/* Controls row - Title field (centered) + Reset Grid */}
      <div className="flex items-center bg-slate-100 dark:bg-slate-700 px-3 py-2 rounded border border-slate-200 dark:border-slate-600 gap-3">
        {/* Title field - for screen_time, centered */}
        {imageType === "screen_time" && (
          <div className="flex items-center gap-2 flex-1 justify-center">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 whitespace-nowrap">
              App/Title
              {!extractedTitle && <AlertTriangle className="w-4 h-4 text-orange-500 ml-1 inline" />}
            </span>
            <input
              type="text"
              value={extractedTitle || ""}
              onChange={(e) => onTitleChange?.(e.target.value)}
              placeholder="Enter app name..."
              aria-label="App or title name"
              disabled={disabled}
              className={`w-52 px-3 py-1.5 text-sm font-medium text-center border-2 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-slate-100 dark:disabled:bg-slate-600 disabled:cursor-not-allowed transition-colors ${
                !extractedTitle
                  ? "border-orange-400 bg-orange-50 dark:bg-orange-900/30 dark:border-orange-600"
                  : "border-slate-300 bg-white dark:bg-slate-600 dark:border-slate-500 dark:text-slate-100 hover:border-slate-400"
              }`}
            />
          </div>
        )}
        {/* Spacer if no title field */}
        {imageType !== "screen_time" && <div className="flex-1" />}
        {/* Reset Grid button */}
        {hasSelection && (
          <button
            onClick={handleReset}
            disabled={disabled}
            className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 text-xs font-medium px-3 py-1.5 border border-red-300 dark:border-red-700 rounded-md hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Reset Grid
          </button>
        )}
      </div>

      {/* Canvas */}
      <div className="bg-slate-800 rounded-lg">
        <canvas
          ref={canvasRef}
          aria-label="Screenshot with grid selection overlay. Use mouse to drag and resize the grid region."
          role="application"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="block"
        />
      </div>

      {/* Status indicator */}
      <div className="text-xs text-center">
        {!hasSelection && (
          <span className="text-slate-500 dark:text-slate-400">Click and drag to select grid</span>
        )}
        {hasSelection && (
          <span className="text-primary-600 font-medium">
            WASD: move | Shift: 10px | Ctrl: resize
          </span>
        )}
      </div>
    </div>
  );
};
