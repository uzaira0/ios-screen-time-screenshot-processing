import { useEffect, useRef, useState, useCallback } from "react";
import { usePreprocessingPipelineService } from "@/core";
import toast from "react-hot-toast";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";
import type { PHIRegion } from "@/core/interfaces/IPreprocessingService";
import { api } from "@/services/apiClient";
export type { PHIRegion };

export interface RecentPHIConfig {
  regions: PHIRegion[];
  label: string;
}

interface PHIRegionEditorProps {
  screenshotId: number;
  isOpen: boolean;
  onClose: () => void;
  onRegionsSaved: () => void;
  onRedactionApplied: () => void;
  inline?: boolean;
  onSaveAndNext?: () => void;
  recentPHIConfigs?: RecentPHIConfig[];
}

type Tool = "draw" | "delete";

const LABELS = [
  "PERSON",
  "IPAD_OWNER",
  "OTHER",
  "UNKNOWN",
];

export const PHIRegionEditor = ({
  screenshotId,
  isOpen,
  onClose,
  onRegionsSaved,
  onRedactionApplied,
  inline = false,
  onSaveAndNext,
  recentPHIConfigs,
}: PHIRegionEditorProps) => {
  const preprocessingService = usePreprocessingPipelineService();
  const { confirm, ConfirmDialog } = useConfirmDialog();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [regions, setRegions] = useState<PHIRegion[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [tool, setTool] = useState<Tool>("draw");
  const [baseScale, setBaseScale] = useState(1);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawCurrent, setDrawCurrent] = useState<{ x: number; y: number } | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isRedacting, setIsRedacting] = useState(false);
  const [whitelistingIndex, setWhitelistingIndex] = useState<number | null>(null);
  const [redactionMethod, setRedactionMethod] = useState(() => {
    try { return localStorage.getItem("phi-recent-redaction-method") || "redbox"; } catch { return "redbox"; }
  });
  const [imageError, setImageError] = useState(false);
  const [regionsLoadError, setRegionsLoadError] = useState(false);
  const [zoom, setZoom] = useState(1);
  const scale = baseScale * zoom;

  // Recent labels tracked in localStorage
  const [recentLabels, setRecentLabels] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem("phi-recent-labels");
      return stored ? JSON.parse(stored) : ["PERSON"];
    } catch { return ["PERSON"]; }
  });
  const lastUsedLabel = recentLabels[0] || "PERSON";

  const trackLabel = (label: string) => {
    setRecentLabels((prev) => {
      const updated = [label, ...prev.filter((l) => l !== label)].slice(0, 3);
      try { localStorage.setItem("phi-recent-labels", JSON.stringify(updated)); } catch { /* ignore */ }
      return updated;
    });
  };

  const trackRedactionMethod = (method: string) => {
    try { localStorage.setItem("phi-recent-redaction-method", method); } catch { /* ignore */ }
  };

  // Close on Escape key (skip in inline mode — queue view handles keyboard)
  useEffect(() => {
    if (!isOpen || inline) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, inline]);

  // Inline mode keyboard shortcuts
  const handleDeleteAutoRef = useRef<() => void>(() => {});
  const handleSaveAndNextRef = useRef<() => void>(() => {});
  handleDeleteAutoRef.current = () => {
    const autoRegions = regions.filter((r) => r.source !== "manual");
    if (autoRegions.length === 0) return;
    setRegions((prev) => prev.filter((r) => r.source === "manual"));
    setSelectedIndex(null);
    toast.success(`Removed ${autoRegions.length} auto-detected region(s)`);
  };
  // handleSaveAndNextRef is assigned after handleSaveAndNext is defined (below the early return)

  useEffect(() => {
    if (!inline) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      // Shift+D: delete all auto-detected regions
      if (e.key === "D" && e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        handleDeleteAutoRef.current();
      }
      // Ctrl/Cmd+Enter: save & next
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleSaveAndNextRef.current();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [inline]);

  // Track which screenshot is loaded to avoid unnecessary reloads and blob URL leaks
  const loadedScreenshotRef = useRef<number | null>(null);
  const blobUrlRef = useRef<string | undefined>(undefined);

  // Reset loaded ref when modal closes so next open re-fetches fresh data
  // (e.g., after applying redaction the image changes)
  useEffect(() => {
    if (!isOpen && !inline) {
      loadedScreenshotRef.current = null;
    }
  }, [isOpen, inline]);

  // Load image and regions on open (inline mode is always "open").
  // Keep showing previous screenshot's data until new data arrives to prevent flicker.
  useEffect(() => {
    if (!isOpen && !inline) return;
    let cancelled = false;
    setSelectedIndex(null);

    // Skip fetches if already loaded for this screenshot (avoids redundant
    // network requests in inline mode where isOpen doesn't toggle)
    if (loadedScreenshotRef.current === screenshotId) return;

    // Don't clear image/regions here — keep showing previous screenshot
    // until new data arrives. Only clear error states.
    setImageError(false);
    setRegionsLoadError(false);

    const prevBlobUrl = blobUrlRef.current;
    const loadingForId = screenshotId;
    loadedScreenshotRef.current = screenshotId;

    // Load the cropped image (not the redacted one)
    preprocessingService.getStageImageUrl(screenshotId, "cropping").then((imageUrl) => {
      if (cancelled) return;
      // Revoke previous blob URL now that new one is ready
      if (prevBlobUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(prevBlobUrl);
      }
      blobUrlRef.current = imageUrl;
      const img = new Image();
      img.onload = () => {
        if (!cancelled) setImage(img);
      };
      img.onerror = () => {
        if (!cancelled) {
          console.error(`[PHIRegionEditor] Failed to load image for screenshot ${screenshotId}`);
          setImage(null);
          setImageError(true);
        }
      };
      img.src = imageUrl;
    }).catch((err) => {
      if (!cancelled) {
        console.error(`[PHIRegionEditor] Failed to get image URL for screenshot ${screenshotId}:`, err);
        setImage(null);
        setImageError(true);
      }
    });

    // Load existing regions — swap in atomically when ready
    preprocessingService.getPHIRegions(screenshotId).then((data: { regions: PHIRegion[] }) => {
      if (!cancelled) setRegions(data.regions || []);
    }).catch((err) => {
      if (!cancelled) {
        console.error(`[PHIRegionEditor] Failed to load PHI regions for screenshot ${screenshotId}:`, err);
        setRegions([]);
        setRegionsLoadError(true);
      }
    });

    return () => {
      cancelled = true;
      // Reset so a re-run of this effect (e.g. React strict mode remount)
      // doesn't skip the fetch due to the early-return guard above.
      if (loadedScreenshotRef.current === loadingForId) {
        loadedScreenshotRef.current = null;
      }
    };
  }, [isOpen, inline, screenshotId, preprocessingService]);

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (blobUrlRef.current?.startsWith("blob:")) {
        URL.revokeObjectURL(blobUrlRef.current);
      }
    };
  }, []);

  // Fit-to-container scale
  useEffect(() => {
    if (!image || !canvasRef.current) return;
    const container = canvasRef.current.parentElement;
    if (!container) return;
    const maxW = container.clientWidth - 10;
    const maxH = window.innerHeight - 200;
    const s = Math.min(maxW / image.naturalWidth, maxH / image.naturalHeight, 1);
    setBaseScale(s);
  }, [image]);

  // Mouse wheel zoom on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      setZoom((z) => Math.min(4, Math.max(0.25, z + delta)));
    };
    canvas.addEventListener("wheel", handleWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", handleWheel);
  }, [image]);

  // Draw canvas
  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !image) return;

    const w = Math.round(image.naturalWidth * scale);
    const h = Math.round(image.naturalHeight * scale);
    canvas.width = w;
    canvas.height = h;

    ctx.drawImage(image, 0, 0, w, h);

    // Draw regions
    regions.forEach((region, i) => {
      const rx = region.x * scale;
      const ry = region.y * scale;
      const rw = region.w * scale;
      const rh = region.h * scale;

      const isAuto = region.source !== "manual";
      const isSelected = i === selectedIndex;

      // Fill
      ctx.fillStyle = isAuto ? "rgba(239, 68, 68, 0.2)" : "rgba(59, 130, 246, 0.2)";
      ctx.fillRect(rx, ry, rw, rh);

      // Border
      ctx.strokeStyle = isSelected ? "#fbbf24" : isAuto ? "#ef4444" : "#3b82f6";
      ctx.lineWidth = isSelected ? 3 : 2;
      ctx.strokeRect(rx, ry, rw, rh);

      // Label
      ctx.font = "10px sans-serif";
      ctx.fillStyle = isAuto ? "#ef4444" : "#3b82f6";
      ctx.fillText(`${i + 1}: ${region.label}`, rx + 2, ry - 3);

      // Resize handles for selected region
      if (isSelected) {
        ctx.fillStyle = "#fbbf24";
        const handles = [
          [rx, ry], [rx + rw, ry], [rx, ry + rh], [rx + rw, ry + rh],
        ];
        for (const [hx, hy] of handles) {
          ctx.fillRect(hx! - 4, hy! - 4, 8, 8);
        }
      }
    });

    // Draw current drawing rect
    if (drawStart && drawCurrent && tool === "draw") {
      const dx = Math.min(drawStart.x, drawCurrent.x) * scale;
      const dy = Math.min(drawStart.y, drawCurrent.y) * scale;
      const dw = Math.abs(drawCurrent.x - drawStart.x) * scale;
      const dh = Math.abs(drawCurrent.y - drawStart.y) * scale;
      ctx.strokeStyle = "#3b82f6";
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.strokeRect(dx, dy, dw, dh);
      ctx.setLineDash([]);
    }
  }, [image, regions, selectedIndex, scale, drawStart, drawCurrent, tool]);

  useEffect(() => {
    drawCanvas();
  }, [drawCanvas]);

  const toImageCoords = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return {
      x: Math.round((e.clientX - rect.left) / scale),
      y: Math.round((e.clientY - rect.top) / scale),
    };
  };

  const findRegionAt = (x: number, y: number): number | null => {
    for (let i = regions.length - 1; i >= 0; i--) {
      const r = regions[i]!;
      if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) return i;
    }
    return null;
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const pt = toImageCoords(e);

    if (tool === "draw") {
      setDrawStart(pt);
      setDrawCurrent(pt);
    } else if (tool === "delete") {
      const idx = findRegionAt(pt.x, pt.y);
      if (idx !== null) {
        setRegions((prev) => prev.filter((_, i) => i !== idx));
        setSelectedIndex(null);
      }
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (tool === "draw" && drawStart) {
      setDrawCurrent(toImageCoords(e));
    }
  };

  const handleMouseUp = () => {
    if (tool === "draw" && drawStart && drawCurrent) {
      const x = Math.min(drawStart.x, drawCurrent.x);
      const y = Math.min(drawStart.y, drawCurrent.y);
      const w = Math.abs(drawCurrent.x - drawStart.x);
      const h = Math.abs(drawCurrent.y - drawStart.y);

      if (w >= 5 && h >= 5) {
        setRegions((prev) => {
          const updated = [
            ...prev,
            { x, y, w, h, label: lastUsedLabel, source: "manual", confidence: 1.0, text: "" },
          ];
          setSelectedIndex(updated.length - 1);
          return updated;
        });
      }
    }
    setDrawStart(null);
    setDrawCurrent(null);
  };

  const getCursor = (): string => {
    return tool === "draw" ? "crosshair" : "not-allowed";
  };

  const updateRegion = (index: number, updates: Partial<PHIRegion>) => {
    if (updates.label) trackLabel(updates.label);
    setRegions((prev) => prev.map((r, i) => i === index ? { ...r, ...updates } : r));
  };

  const deleteRegion = (index: number) => {
    setRegions((prev) => prev.filter((_, i) => i !== index));
    if (selectedIndex === index) setSelectedIndex(null);
    else if (selectedIndex !== null && selectedIndex > index) setSelectedIndex(selectedIndex - 1);
  };

  const handleWhitelist = async (index: number) => {
    const region = regions[index];
    const text = region?.text?.trim();
    if (!text) {
      toast.error("No text to whitelist for this region");
      return;
    }
    setWhitelistingIndex(index);
    try {
      await api.preprocessing.addToPhiWhitelist(text);
      // Remove this region and re-apply redaction with remaining regions
      const remaining = regions.filter((_, i) => i !== index);
      setRegions(remaining);
      setSelectedIndex(null);
      await preprocessingService.savePHIRegions(screenshotId, { regions: remaining, preset: "manual" });
      onRegionsSaved();
      try {
        await preprocessingService.applyRedaction(screenshotId, { regions: remaining, redaction_method: redactionMethod });
        onRedactionApplied();
      } catch { /* redaction not applicable yet */ }
      toast.success(`"${text}" whitelisted & redaction updated`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to whitelist");
    } finally {
      setWhitelistingIndex(null);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await preprocessingService.savePHIRegions(screenshotId, { regions, preset: "manual" });
      onRegionsSaved();
      // Auto re-apply redaction so the redacted image reflects current regions
      try {
        await preprocessingService.applyRedaction(screenshotId, { regions, redaction_method: redactionMethod });
        onRedactionApplied();
        toast.success(`Saved ${regions.length} region(s) & updated redaction`);
      } catch {
        // Redaction may not be applicable (e.g., no cropped image yet)
        toast.success(`Saved ${regions.length} PHI region(s)`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setIsSaving(false);
    }
  };

  const handleRedact = async () => {
    const confirmed = await confirm({
      title: "Apply Redaction",
      message: `Apply ${redactionMethod} redaction to ${regions.length} region(s)? This will save regions and create a new redacted image.`,
      confirmLabel: "Apply Redaction",
      variant: "warning",
    });
    if (!confirmed) return;

    setIsRedacting(true);
    try {
      // Save regions first, then apply redaction
      await preprocessingService.savePHIRegions(screenshotId, { regions, preset: "manual" });
      onRegionsSaved();
      try {
        await preprocessingService.applyRedaction(screenshotId, { regions, redaction_method: redactionMethod });
      } catch (redactErr) {
        toast.error(redactErr instanceof Error ? `Regions saved, but redaction failed: ${redactErr.message}` : "Regions saved, but redaction failed");
        return;
      }
      trackRedactionMethod(redactionMethod);
      toast.success("Regions saved & redaction applied");
      onRedactionApplied();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setIsRedacting(false);
    }
  };

  if (!isOpen && !inline) return null;

  const autoCount = regions.filter((r) => r.source !== "manual").length;
  const manualCount = regions.length - autoCount;

  const handleSaveAndNext = async () => {
    setIsSaving(true);
    try {
      await preprocessingService.savePHIRegions(screenshotId, { regions, preset: "manual" });
      onRegionsSaved();
      // Auto re-apply redaction
      try {
        await preprocessingService.applyRedaction(screenshotId, { regions, redaction_method: redactionMethod });
        onRedactionApplied();
      } catch { /* redaction not applicable yet */ }
      toast.success(`Saved ${regions.length} region(s) & updated redaction`);
      onSaveAndNext?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setIsSaving(false);
    }
  };

  // Wire up the ref so the keyboard shortcut can call it
  handleSaveAndNextRef.current = onSaveAndNext ? handleSaveAndNext : () => {};

  const editorContent = (
    <div className="flex-1 flex overflow-hidden">
      {/* Canvas area */}
      <div className="flex-1 overflow-auto p-4 flex items-center justify-center">
        {imageError ? (
          <div className="flex flex-col items-center justify-center h-64 gap-2">
            <span className="text-red-500 text-sm">Failed to load image</span>
            {!inline && (
              <button
                onClick={onClose}
                className="px-3 py-1 text-sm text-slate-600 border border-slate-300 rounded hover:bg-slate-50"
              >
                Close
              </button>
            )}
          </div>
        ) : image ? (
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`PHI region editor for screenshot ${screenshotId}. ${regions.length} regions marked. Use the toolbar to select Draw or Delete tools.`}
            style={{ cursor: getCursor() }}
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

      {/* Sidebar */}
      <div className="w-80 border-l dark:border-slate-700 flex flex-col">
        {/* Toolbar */}
        <div className="flex items-center gap-1 p-3 border-b dark:border-slate-700">
          {(["draw", "delete"] as Tool[]).map((t) => (
            <button
              key={t}
              onClick={() => setTool(t)}
              aria-label={`${t === "draw" ? "Draw" : "Delete"} tool`}
              aria-pressed={tool === t}
              className={`px-3 py-1.5 text-xs rounded font-medium ${
                tool === t
                  ? "bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400 border border-primary-300 dark:border-primary-700"
                  : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 border border-transparent"
              }`}
            >
              {t === "draw" ? "Draw" : "Delete"}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}
              className="px-2 py-1 text-xs rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600"
              title="Zoom out"
            >
              −
            </button>
            <span className="text-xs text-slate-500 dark:text-slate-400 w-10 text-center">{Math.round(zoom * 100)}%</span>
            <button
              onClick={() => setZoom((z) => Math.min(4, z + 0.25))}
              className="px-2 py-1 text-xs rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600"
              title="Zoom in"
            >
              +
            </button>
            <button
              onClick={() => setZoom(1)}
              className="px-1.5 py-1 text-[10px] rounded bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-600"
              title="Reset zoom"
            >
              Fit
            </button>
          </div>
        </div>

        {/* Region list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {/* Recent labels (quick apply to new drawings) */}
          {recentLabels.length > 1 && (
            <div className="mb-2">
              <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">Next label:</div>
              <div className="flex flex-wrap gap-1">
                {recentLabels.map((label) => (
                  <button
                    key={label}
                    onClick={() => trackLabel(label)}
                    className={`px-2 py-0.5 text-[10px] rounded font-medium transition-colors ${
                      label === lastUsedLabel
                        ? "bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400 border border-primary-300 dark:border-primary-700"
                        : "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 border border-transparent"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {/* Recent region configs */}
          {recentPHIConfigs && recentPHIConfigs.length > 0 && (
            <div className="mb-3">
              <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1.5">Recent Regions</div>
              <div className="flex flex-wrap gap-1.5">
                {recentPHIConfigs.map((cfg, i) => (
                  <button
                    key={i}
                    onClick={async () => {
                      if (regions.length > 0) {
                        const ok = await confirm({ title: "Replace Regions", message: `Replace ${regions.length} existing region(s) with this config?`, confirmLabel: "Replace", variant: "warning" });
                        if (!ok) return;
                      }
                      setRegions(cfg.regions);
                      setSelectedIndex(null);
                    }}
                    className="px-2 py-1 text-xs bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-600 rounded hover:bg-primary-50 dark:hover:bg-primary-900/30 hover:border-primary-300 hover:text-primary-700 transition-colors"
                    title={`Apply ${cfg.regions.length} region(s): ${cfg.label}`}
                  >
                    {cfg.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="text-xs text-slate-500 dark:text-slate-400 mb-2">
            {autoCount} auto-detected, {manualCount} manual
          </div>
          {regions.map((region, i) => (
            <div
              key={i}
              className={`flex flex-col gap-1 p-2 rounded text-xs cursor-pointer ${
                i === selectedIndex ? "bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-700" : "hover:bg-slate-50 dark:hover:bg-slate-700 border border-transparent"
              }`}
              onClick={() => setSelectedIndex(i)}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-slate-400 w-4">{i + 1}</span>
                <span className="text-slate-500">
                  {region.x},{region.y} {region.w}x{region.h}
                </span>
                <select
                  value={region.label}
                  onChange={(e) => updateRegion(i, { label: e.target.value })}
                  className="text-xs border dark:border-slate-600 rounded px-1 py-0.5 flex-1 dark:bg-slate-700 dark:text-slate-200"
                  onClick={(e) => e.stopPropagation()}
                >
                  {(!LABELS.includes(region.label) ? [region.label, ...LABELS] : LABELS).map((l) => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] ${
                    region.source === "manual" ? "bg-primary-100 text-primary-600" : "bg-red-100 text-red-600"
                  }`}
                >
                  {region.source === "manual" ? "M" : "A"}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); deleteRegion(i); }}
                  className="text-slate-400 hover:text-red-500 leading-none"
                  title="Delete region"
                  aria-label={`Delete region ${i + 1}`}
                >
                  &times;
                </button>
              </div>
              {region.text && (
                <div className="flex items-center gap-1 pl-6">
                  <span
                    className="italic text-slate-500 dark:text-slate-400 truncate flex-1"
                    title={region.text}
                  >
                    "{region.text}"
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleWhitelist(i); }}
                    disabled={whitelistingIndex === i}
                    className="px-1.5 py-0.5 text-[10px] rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-800/40 disabled:opacity-50 shrink-0"
                    title={`Whitelist "${region.text}" — never flag this text again`}
                  >
                    {whitelistingIndex === i ? "..." : "Whitelist"}
                  </button>
                </div>
              )}
            </div>
          ))}
          {regionsLoadError && (
            <div className="text-center text-red-500 dark:text-red-400 py-4 text-sm font-medium bg-red-50 dark:bg-red-900/20 rounded border border-red-200 dark:border-red-800 mx-2">
              Failed to load PHI regions — regions may exist but could not be fetched. Do not skip redaction.
            </div>
          )}
          {regions.length === 0 && !regionsLoadError && (
            <div className="text-center text-slate-400 dark:text-slate-500 py-8 text-sm">
              No PHI regions. Use Draw tool to add regions.
            </div>
          )}
        </div>

        {/* Redaction method */}
        <div className="p-3 border-t dark:border-slate-700 space-y-3">
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500 dark:text-slate-400">Method:</label>
            <select
              value={redactionMethod}
              onChange={(e) => { setRedactionMethod(e.target.value); trackRedactionMethod(e.target.value); }}
              className="text-xs border dark:border-slate-600 rounded px-2 py-1 flex-1 dark:bg-slate-700 dark:text-slate-200"
            >
              <option value="redbox">Red Box</option>
              <option value="blackbox">Black Box</option>
              <option value="pixelate">Pixelate</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex-1 px-3 py-2 text-xs font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded hover:bg-primary-100 disabled:bg-slate-100 disabled:text-slate-400 disabled:border-slate-200"
            >
              {isSaving ? "Saving..." : "Save Regions"}
            </button>
            <button
              onClick={handleRedact}
              disabled={isRedacting || regions.length === 0}
              className="flex-1 px-3 py-2 text-xs font-medium text-white bg-orange-600 rounded hover:bg-orange-700 disabled:bg-slate-400 disabled:text-slate-200"
            >
              {isRedacting ? "Redacting..." : "Apply Redaction"}
            </button>
          </div>
          {onSaveAndNext && (
            <button
              onClick={handleSaveAndNext}
              disabled={isSaving}
              className="w-full px-3 py-2 text-xs font-medium text-white bg-green-600 rounded hover:bg-green-700 disabled:bg-slate-400 disabled:text-slate-200"
            >
              {isSaving ? "Saving..." : "Save & Next"}
            </button>
          )}
        </div>
      </div>
    </div>
  );

  if (inline) {
    return (
      <div className="flex flex-col h-full bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        {editorContent}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-[95vw] h-[95vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b dark:border-slate-700">
          <h3 className="text-lg font-semibold dark:text-slate-100">PHI Region Editor - Screenshot #{screenshotId}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-xl leading-none" aria-label="Close PHI region editor">&times;</button>
        </div>
        {editorContent}
      </div>
      {ConfirmDialog}
    </div>
  );
};
