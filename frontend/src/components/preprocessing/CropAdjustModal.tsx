import { useEffect, useRef, useState, useCallback } from "react";
import { usePreprocessingPipelineService } from "@/core";
import toast from "react-hot-toast";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";

export interface CropRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface CropAdjustModalProps {
  screenshotId: number;
  isOpen: boolean;
  onClose: () => void;
  onCropApplied: () => void;
  initialCrop?: CropRect | undefined;
  inline?: boolean | undefined;
  onApplyAndNext?: (() => void) | undefined;
  recentCrops?: CropRect[] | undefined;
}

type DragMode = "none" | "move" | "top" | "bottom" | "left" | "right" | "tl" | "tr" | "bl" | "br";

const HANDLE_SIZE = 8;

export const CropAdjustModal = ({
  screenshotId,
  isOpen,
  onClose,
  onCropApplied,
  initialCrop,
  inline = false,
  onApplyAndNext,
  recentCrops,
}: CropAdjustModalProps) => {
  const preprocessingService = usePreprocessingPipelineService();
  const { confirm, ConfirmDialog } = useConfirmDialog();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [crop, setCrop] = useState<CropRect>({ left: 0, top: 0, right: 100, bottom: 100 });
  const [scale, setScale] = useState(1);
  const [dragMode, setDragMode] = useState<DragMode>("none");
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [cropStart, setCropStart] = useState<CropRect>({ left: 0, top: 0, right: 100, bottom: 100 });
  const [isApplying, setIsApplying] = useState(false);
  const [imageError, setImageError] = useState(false);

  // localStorage-backed recent crops (used when recentCrops prop is not provided, e.g. modal mode)
  const [storedRecentCrops, setStoredRecentCrops] = useState<CropRect[]>(() => {
    try {
      const stored = localStorage.getItem("crop-recent-configs");
      return stored ? JSON.parse(stored) : [];
    } catch { return []; }
  });

  const trackCrop = (c: CropRect) => {
    const key = `${c.left},${c.top},${c.right},${c.bottom}`;
    setStoredRecentCrops((prev) => {
      const deduped = prev.filter((r) => `${r.left},${r.top},${r.right},${r.bottom}` !== key);
      const updated = [c, ...deduped].slice(0, 5);
      try { localStorage.setItem("crop-recent-configs", JSON.stringify(updated)); } catch { /* ignore */ }
      return updated;
    });
  };

  // Merge prop-provided recent crops with localStorage-backed ones
  const effectiveRecentCrops = recentCrops && recentCrops.length > 0 ? recentCrops : storedRecentCrops;

  // Close on Escape key (skip in inline mode — queue view handles keyboard)
  useEffect(() => {
    if (!isOpen || inline) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, inline]);

  // Keep a ref to initialCrop so the image-load effect doesn't re-trigger on
  // every render when the parent computes a new (structurally equal) object.
  const initialCropRef = useRef(initialCrop);
  initialCropRef.current = initialCrop;

  // Load original image (inline mode is always "open")
  useEffect(() => {
    if (!isOpen && !inline) return;
    setImageError(false);
    setImage(null);
    let cancelled = false;
    let blobUrl: string | undefined;
    const img = new Image();
    // Don't set crossOrigin — images are same-origin through the proxy.
    // Setting crossOrigin="anonymous" forces a CORS preflight that fails.
    img.onload = () => {
      if (cancelled) return;
      setImage(img);
      const ic = initialCropRef.current;
      if (ic) {
        setCrop(ic);
      } else {
        setCrop({ left: 0, top: 0, right: img.naturalWidth, bottom: img.naturalHeight });
      }
    };
    img.onerror = () => { if (!cancelled) setImageError(true); };
    preprocessingService.getOriginalImageUrl(screenshotId).then((url) => {
      if (cancelled) {
        if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
        return;
      }
      blobUrl = url;
      if (url) {
        img.src = url;
      } else {
        setImageError(true);
      }
    }).catch((e) => { console.error("Failed to load image for crop adjustment:", e); if (!cancelled) setImageError(true); });
    return () => {
      cancelled = true;
      if (blobUrl?.startsWith("blob:")) URL.revokeObjectURL(blobUrl);
    };
  }, [isOpen, inline, screenshotId, preprocessingService]);

  // Calculate scale to fit canvas — use most of the viewport
  useEffect(() => {
    if (!image || !canvasRef.current) return;
    const container = canvasRef.current.parentElement;
    if (!container) return;
    const maxW = container.clientWidth - 20;
    const maxH = window.innerHeight * 0.82; // Use ~82% of viewport height for canvas
    const s = Math.min(maxW / image.naturalWidth, maxH / image.naturalHeight, 1);
    setScale(s);
  }, [image]);

  // Draw main canvas with crop overlay
  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !image) return;

    const w = Math.round(image.naturalWidth * scale);
    const h = Math.round(image.naturalHeight * scale);
    canvas.width = w;
    canvas.height = h;

    // Draw image
    ctx.drawImage(image, 0, 0, w, h);

    // Draw dark overlay outside crop
    ctx.fillStyle = "rgba(0, 0, 0, 0.5)";
    const sl = crop.left * scale;
    const st = crop.top * scale;
    const sr = crop.right * scale;
    const sb = crop.bottom * scale;
    ctx.fillRect(0, 0, w, st); // top
    ctx.fillRect(0, sb, w, h - sb); // bottom
    ctx.fillRect(0, st, sl, sb - st); // left
    ctx.fillRect(sr, st, w - sr, sb - st); // right

    // Draw crop border
    ctx.strokeStyle = "#3b82f6";
    ctx.lineWidth = 2;
    ctx.strokeRect(sl, st, sr - sl, sb - st);

    // Draw handles
    ctx.fillStyle = "#3b82f6";
    const handles = [
      [sl, st], [sr, st], [sl, sb], [sr, sb], // corners
      [(sl + sr) / 2, st], [(sl + sr) / 2, sb], // top/bottom center
      [sl, (st + sb) / 2], [sr, (st + sb) / 2], // left/right center
    ];
    for (const [hx, hy] of handles) {
      ctx.fillRect(hx! - HANDLE_SIZE / 2, hy! - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
    }
  }, [image, crop, scale]);

  useEffect(() => {
    drawCanvas();
  }, [drawCanvas]);

  // Draw preview
  useEffect(() => {
    const canvas = previewRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !image) return;

    const cropW = crop.right - crop.left;
    const cropH = crop.bottom - crop.top;
    if (cropW <= 0 || cropH <= 0) return;

    const maxPreviewW = 500;
    const maxPreviewH = 600;
    const previewScale = Math.min(maxPreviewW / cropW, maxPreviewH / cropH, 1);
    canvas.width = Math.round(cropW * previewScale);
    canvas.height = Math.round(cropH * previewScale);

    ctx.drawImage(
      image,
      crop.left, crop.top, cropW, cropH,
      0, 0, canvas.width, canvas.height,
    );
  }, [image, crop]);

  // Hit test for drag mode
  const hitTest = (mx: number, my: number): DragMode => {
    const sl = crop.left * scale;
    const st = crop.top * scale;
    const sr = crop.right * scale;
    const sb = crop.bottom * scale;
    const hs = HANDLE_SIZE + 4;

    // Corner handles
    if (Math.abs(mx - sl) < hs && Math.abs(my - st) < hs) return "tl";
    if (Math.abs(mx - sr) < hs && Math.abs(my - st) < hs) return "tr";
    if (Math.abs(mx - sl) < hs && Math.abs(my - sb) < hs) return "bl";
    if (Math.abs(mx - sr) < hs && Math.abs(my - sb) < hs) return "br";

    // Edge handles
    if (Math.abs(my - st) < hs && mx > sl && mx < sr) return "top";
    if (Math.abs(my - sb) < hs && mx > sl && mx < sr) return "bottom";
    if (Math.abs(mx - sl) < hs && my > st && my < sb) return "left";
    if (Math.abs(mx - sr) < hs && my > st && my < sb) return "right";

    // Inside = move
    if (mx > sl && mx < sr && my > st && my < sb) return "move";

    return "none";
  };

  const getCursor = (mode: DragMode): string => {
    switch (mode) {
      case "tl": case "br": return "nwse-resize";
      case "tr": case "bl": return "nesw-resize";
      case "top": case "bottom": return "ns-resize";
      case "left": case "right": return "ew-resize";
      case "move": return "move";
      default: return "crosshair";
    }
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const mode = hitTest(mx, my);
    if (mode === "none") return;
    setDragMode(mode);
    setDragStart({ x: mx, y: my });
    setCropStart({ ...crop });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    if (dragMode === "none") {
      const mode = hitTest(mx, my);
      if (canvasRef.current) canvasRef.current.style.cursor = getCursor(mode);
      return;
    }

    if (!image) return;
    const dx = (mx - dragStart.x) / scale;
    const dy = (my - dragStart.y) / scale;
    const imgW = image.naturalWidth;
    const imgH = image.naturalHeight;

    let { left, top, right, bottom } = cropStart;

    switch (dragMode) {
      case "move":
        left += dx; right += dx; top += dy; bottom += dy;
        // Clamp to image bounds
        if (left < 0) { right -= left; left = 0; }
        if (top < 0) { bottom -= top; top = 0; }
        if (right > imgW) { left -= right - imgW; right = imgW; }
        if (bottom > imgH) { top -= bottom - imgH; bottom = imgH; }
        break;
      case "left": left = Math.max(0, Math.min(right - 10, cropStart.left + dx)); break;
      case "right": right = Math.min(imgW, Math.max(left + 10, cropStart.right + dx)); break;
      case "top": top = Math.max(0, Math.min(bottom - 10, cropStart.top + dy)); break;
      case "bottom": bottom = Math.min(imgH, Math.max(top + 10, cropStart.bottom + dy)); break;
      case "tl": left = Math.max(0, Math.min(right - 10, cropStart.left + dx)); top = Math.max(0, Math.min(bottom - 10, cropStart.top + dy)); break;
      case "tr": right = Math.min(imgW, Math.max(left + 10, cropStart.right + dx)); top = Math.max(0, Math.min(bottom - 10, cropStart.top + dy)); break;
      case "bl": left = Math.max(0, Math.min(right - 10, cropStart.left + dx)); bottom = Math.min(imgH, Math.max(top + 10, cropStart.bottom + dy)); break;
      case "br": right = Math.min(imgW, Math.max(left + 10, cropStart.right + dx)); bottom = Math.min(imgH, Math.max(top + 10, cropStart.bottom + dy)); break;
    }

    setCrop({
      left: Math.round(left),
      top: Math.round(top),
      right: Math.round(right),
      bottom: Math.round(bottom),
    });
  };

  const handleMouseUp = () => {
    setDragMode("none");
  };

  const handleApply = async () => {
    const confirmed = await confirm({
      title: "Apply Crop",
      message: `Apply crop (${crop.right - crop.left}x${crop.bottom - crop.top}px)? This will overwrite the current cropped image and invalidate downstream stages.`,
      confirmLabel: "Apply Crop",
      variant: "warning",
    });
    if (!confirmed) return;

    setIsApplying(true);
    try {
      await preprocessingService.applyManualCrop(screenshotId, crop);
      trackCrop(crop);
      toast.success("Manual crop applied");
      onCropApplied();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Crop failed");
    } finally {
      setIsApplying(false);
    }
  };

  if (!isOpen && !inline) return null;

  const cropW = crop.right - crop.left;
  const cropH = crop.bottom - crop.top;

  const handleApplyAndNext = async () => {
    setIsApplying(true);
    try {
      await preprocessingService.applyManualCrop(screenshotId, crop);
      trackCrop(crop);
      toast.success("Manual crop applied");
      onCropApplied();
      onApplyAndNext?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Crop failed");
    } finally {
      setIsApplying(false);
    }
  };

  const editorContent = (
    <>
      {/* Content */}
      <div className="flex-1 flex overflow-hidden p-6 gap-6 min-h-0">
        {/* Left: Main canvas */}
        <div className="flex-1 overflow-auto flex items-start justify-center">
          {imageError ? (
            <div className="flex flex-col items-center justify-center h-64 gap-2">
              <span className="text-red-500 text-sm">Failed to load image</span>
              {!inline && (
                <button
                  onClick={onClose}
                  className="px-3 py-1 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded hover:bg-slate-50 dark:hover:bg-slate-700"
                >
                  Close
                </button>
              )}
            </div>
          ) : image ? (
            <canvas
              ref={canvasRef}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            />
          ) : (
            <div className="flex items-center justify-center h-64 gap-2">
              <span className="inline-block w-5 h-5 border-2 border-slate-300 border-t-primary-500 rounded-full animate-spin" />
              <span className="text-slate-400">Loading image...</span>
            </div>
          )}
        </div>

        {/* Right: Preview + controls */}
        <div className="w-[420px] shrink-0 flex flex-col gap-4 overflow-auto">
          {/* Recent crops */}
          {effectiveRecentCrops.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1.5">Recent Crops</div>
              <div className="flex flex-wrap gap-1.5">
                {effectiveRecentCrops.map((rc, i) => (
                  <button
                    key={i}
                    onClick={() => setCrop(rc)}
                    className="px-2 py-1 text-xs font-mono bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-600 rounded hover:bg-primary-50 dark:hover:bg-primary-900/30 hover:border-primary-300 hover:text-primary-700 transition-colors"
                    title={`Left: ${rc.left}, Top: ${rc.top}, Right: ${rc.right}, Bottom: ${rc.bottom}`}
                  >
                    {rc.right - rc.left}&times;{rc.bottom - rc.top}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="text-sm font-medium text-slate-700 dark:text-slate-300">Preview</div>
          <div className="border dark:border-slate-600 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-700 flex items-center justify-center min-h-[300px]">
            <canvas ref={previewRef} />
          </div>

          {/* Numeric inputs */}
          <div className="grid grid-cols-2 gap-2">
            {(["left", "top", "right", "bottom"] as const).map((field) => (
              <div key={field} className="flex items-center gap-1">
                <label className="text-xs text-slate-500 dark:text-slate-400 w-12 capitalize">{field}:</label>
                <input
                  type="number"
                  value={crop[field]}
                  onChange={(e) => setCrop({ ...crop, [field]: Math.max(0, parseInt(e.target.value) || 0) })}
                  className="w-full text-xs border border-slate-200 dark:border-slate-600 rounded px-2 py-1 dark:bg-slate-700 dark:text-slate-200"
                  min={0}
                />
              </div>
            ))}
          </div>

          <div className="text-xs text-slate-500 dark:text-slate-400">
            Crop: {cropW} x {cropH}px
            {image && <span className="ml-2">(Original: {image.naturalWidth} x {image.naturalHeight})</span>}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-3 px-6 py-3 border-t dark:border-slate-700 shrink-0">
        {initialCropRef.current && (
          <button
            onClick={() => setCrop(initialCropRef.current!)}
            className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 focus-ring mr-auto"
            title="Reset crop to the auto-detected values"
          >
            Reset to Auto
          </button>
        )}
        {!inline && (
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 focus-ring"
          >
            Cancel
          </button>
        )}
        <button
          onClick={handleApply}
          disabled={isApplying || cropW < 10 || cropH < 10}
          className="px-6 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 focus-ring"
        >
          {isApplying ? "Applying..." : "Apply Crop"}
        </button>
        {onApplyAndNext && (
          <button
            onClick={handleApplyAndNext}
            disabled={isApplying || cropW < 10 || cropH < 10}
            className="px-6 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-50"
          >
            {isApplying ? "Applying..." : "Apply & Next"}
          </button>
        )}
      </div>
    </>
  );

  if (inline) {
    return (
      <div className="flex flex-col h-full bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        {editorContent}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-[98vw] h-[94vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b dark:border-slate-700 shrink-0">
          <h3 className="text-lg font-semibold dark:text-slate-100">Adjust Crop - Screenshot #{screenshotId}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-xl leading-none" aria-label="Close crop editor">&times;</button>
        </div>
        {editorContent}
      </div>
      {ConfirmDialog}
    </div>
  );
};
