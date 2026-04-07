import { useRef, useEffect, useState, useCallback } from "react";
import type { HourlyData, Consensus, GridCoordinates } from "@/types";
import { loadImage } from "@/utils/imageUtils";
import clsx from "clsx";

interface HourlyUsageOverlayProps {
  data: HourlyData;
  onChange: (hour: number, value: number) => void;
  imageUrl: string;
  gridCoords: GridCoordinates | null;
  consensus?: Consensus;
  readOnly?: boolean;
}

export const HourlyUsageOverlay = ({
  data,
  onChange,
  imageUrl,
  gridCoords,
  consensus,
  readOnly = false,
}: HourlyUsageOverlayProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [canvasReady, setCanvasReady] = useState(false);
  const containerWidthRef = useRef(800);
  const loadedImageRef = useRef<HTMLImageElement | null>(null);
  const gridCoordsRef = useRef(gridCoords);
  gridCoordsRef.current = gridCoords;
  const rafRef = useRef<number | null>(null);
  // Stable boolean — only changes when gridCoords validity changes, not on every reference change
  const hasValidGrid = !!(gridCoords && gridCoords.upper_left.x !== 0);

  // Redraw canvas from cached image (stable — reads everything from refs)
  const redrawCanvas = useCallback(() => {
    const img = loadedImageRef.current;
    const canvas = canvasRef.current;
    const gc = gridCoordsRef.current;
    if (!img || !canvas || !gc || gc.upper_left.x === 0) return;

    const cropX = gc.upper_left.x;
    const cropY = gc.upper_left.y;
    const cropWidth = gc.lower_right.x - gc.upper_left.x;
    const cropHeight = gc.lower_right.y - gc.upper_left.y;
    if (cropWidth <= 0 || cropHeight <= 0) return;

    const graphHeight = 200;
    const targetWidth = containerWidthRef.current;
    canvas.width = targetWidth;
    canvas.height = graphHeight;

    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.drawImage(img, cropX, cropY, cropWidth, cropHeight, 0, 0, targetWidth, graphHeight);
    }
  }, []);

  // Handle resize — RAF-coalesced redraw, no image reload
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidthRef.current = entry.contentRect.width;
      }
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        redrawCanvas();
      });
    });

    observer.observe(containerRef.current);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      observer.disconnect();
    };
  }, [redrawCanvas]);

  // Redraw when grid coords change (user drags grid on left panel)
  useEffect(() => {
    if (loadedImageRef.current && hasValidGrid) {
      redrawCanvas();
    }
  }, [gridCoords, hasValidGrid, redrawCanvas]);

  // Load image when imageUrl changes or grid becomes valid.
  // hasValidGrid is a primitive boolean so it won't trigger on unstable object refs.
  useEffect(() => {
    let isMounted = true;

    if (!hasValidGrid || !imageUrl) {
      setCanvasReady(false);
      return;
    }

    const loadAndCropImage = async () => {
      try {
        const img = await loadImage(imageUrl);
        if (!isMounted) return;
        loadedImageRef.current = img;
        redrawCanvas();
        setCanvasReady(true);
      } catch (err) {
        console.error("Failed to load cropped image:", err);
        if (isMounted) {
          setCanvasReady(false);
        }
      }
    };

    loadAndCropImage();

    return () => {
      isMounted = false;
      loadedImageRef.current = null;
    };
  }, [imageUrl, hasValidGrid, redrawCanvas]);

  const handleChange = (hour: number, delta: number) => {
    const currentValue = data[hour] || 0;
    const newValue = Math.max(0, Math.min(60, currentValue + delta));
    onChange(hour, newValue);
  };

  const handleInputChange = (hour: number, value: string) => {
    const numValue = parseFloat(value) || 0;
    if (numValue < 0 || numValue > 60) return;
    // Round to 2 decimal places to avoid floating point issues
    onChange(hour, Math.round(numValue * 100) / 100);
  };

  // Format value for display: show decimal only if meaningful
  const formatValue = (val: number): string => {
    const rounded = Math.round(val * 10) / 10;
    return rounded % 1 === 0 ? String(Math.round(rounded)) : String(rounded);
  };

  const getDisagreementLevel = (
    hour: number,
  ): "none" | "minor" | "major" | null => {
    if (!consensus) return null;
    const disagreement = consensus.disagreements.find((d) => d.hour === hour);
    if (!disagreement) return "none";
    const currentValue = data[hour] || 0;
    const diff = Math.abs(currentValue - disagreement.consensus_value);
    if (diff === 0) return "none";
    if (diff <= 5) return "minor";
    return "major";
  };

  const getCellClassName = (hour: number) => {
    const level = getDisagreementLevel(hour);
    return clsx(
      "w-full text-center text-[10px] font-medium border rounded-md focus:outline-none focus:ring-2 transition-all py-0.5",
      {
        "bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400": level === "none",
        "bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200 dark:border-yellow-800 text-yellow-700 dark:text-yellow-400": level === "minor",
        "bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400": level === "major",
        "bg-white dark:bg-slate-700 border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-200 focus:ring-primary-500 focus:border-primary-500":
          level === null,
        "bg-slate-50 dark:bg-slate-800 text-slate-400 cursor-not-allowed": readOnly,
      },
    );
  };

  const graphHeight = 200;

  return (
    <div className="w-full" ref={containerRef} data-testid="hourly-editor">
      {/* Graph Area with Overlay */}
      <div
        className="relative bg-white rounded-lg overflow-hidden border border-slate-200"
        style={{ height: graphHeight }}
      >
        {/* Background: Cropped screenshot */}
        <canvas
          ref={canvasRef}
          aria-label="Cropped screenshot showing hourly usage graph"
          role="img"
          className={`absolute inset-0 w-full h-full transition-opacity duration-300 ${
            hasValidGrid && canvasReady ? "opacity-60" : "opacity-0"
          }`}
        />

        {(!hasValidGrid || !canvasReady) && (
          <div className="absolute inset-0 w-full h-full bg-slate-50 flex items-center justify-center text-slate-400 text-sm">
            {hasValidGrid ? "Loading..." : "Select grid area to view overlay"}
          </div>
        )}

        {/* Overlay: Hourly bars grid - EXACTLY 24 columns */}
        <div
          className="absolute inset-0 w-full h-full grid"
          style={{
            gridTemplateColumns: "repeat(24, 1fr)",
          }}
        >
          {Array.from({ length: 24 }, (_, i) => {
            const value = data[i] || 0;
            const heightPercentage = (value / 60) * 100;

            return (
              <div
                key={i}
                className="flex flex-col h-full justify-end items-center"
              >
                {/* Bar - only render if value > 0 */}
                {value > 0 ? (
                  <div
                    className="w-4/5 bg-blue-500/70 transition-all duration-300 hover:bg-blue-500/80 rounded-t-md"
                    style={{
                      height: `${heightPercentage}%`,
                      minHeight: "2px",
                    }}
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      {/* Controls - EXACTLY 24 columns to match the graph above */}
      <div
        className="w-full grid gap-2 mt-4"
        style={{ gridTemplateColumns: "repeat(24, 1fr)" }}
      >
        {Array.from({ length: 24 }, (_, i) => {
          const value = data[i] || 0;

          return (
            <div key={i} className="flex flex-col items-center gap-1">
              {/* X-Axis Label */}
              <div className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold text-center">
                {i}h
              </div>

              <button
                type="button"
                onClick={() => handleChange(i, 1)}
                disabled={readOnly}
                className="w-full h-5 flex items-center justify-center text-[10px] bg-slate-100 dark:bg-slate-700 hover:bg-primary-50 dark:hover:bg-primary-900/30 hover:text-primary-600 rounded text-slate-600 dark:text-slate-400 disabled:opacity-50 transition-colors"
              >
                ▲
              </button>
              <input
                type="text"
                inputMode="decimal"
                pattern="[0-9]*\.?[0-9]*"
                value={formatValue(value)}
                onChange={(e) => handleInputChange(i, e.target.value)}
                disabled={readOnly}
                aria-label={`Usage for hour ${i === 0 ? "12 AM" : i < 12 ? `${i} AM` : i === 12 ? "12 PM" : `${i - 12} PM`}`}
                className={getCellClassName(i)}
                style={{ appearance: "textfield" }}
                data-testid={`hour-input-${i}`}
              />
              <button
                type="button"
                onClick={() => handleChange(i, -1)}
                disabled={readOnly}
                className="w-full h-5 flex items-center justify-center text-[10px] bg-slate-100 dark:bg-slate-700 hover:bg-primary-50 dark:hover:bg-primary-900/30 hover:text-primary-600 rounded text-slate-600 dark:text-slate-400 disabled:opacity-50 transition-colors"
              >
                ▼
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};
