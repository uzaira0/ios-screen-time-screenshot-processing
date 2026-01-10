import { useRef, useEffect, useState } from "react";
import type { GridCoordinates } from "@/types";
import { loadImage } from "@/utils/imageUtils";

interface CroppedGraphViewerProps {
  imageUrl: string;
  gridCoords: GridCoordinates | null;
  targetWidth?: number;
}

export const CroppedGraphViewer = ({
  imageUrl,
  gridCoords,
  targetWidth = 800,
}: CroppedGraphViewerProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    // Reset error when imageUrl changes so the component recovers after
    // a transient failure (e.g., revoked blob URL replaced by a fresh one).
    setError(false);

    if (!gridCoords || gridCoords.upper_left.x === 0 || !imageUrl) {
      return;
    }

    const loadAndCropImage = async () => {
      try {
        const img = await loadImage(imageUrl);
        const canvas = canvasRef.current;
        const container = containerRef.current;
        if (!canvas || !container) return;

        const cropX = gridCoords.upper_left.x;
        const cropY = gridCoords.upper_left.y;
        const cropWidth = gridCoords.lower_right.x - gridCoords.upper_left.x;
        const cropHeight = gridCoords.lower_right.y - gridCoords.upper_left.y;

        if (cropWidth <= 0 || cropHeight <= 0) return;

        // Fixed height for consistency
        const graphHeight = 200;
        const containerWidth = container.clientWidth || targetWidth;

        canvas.width = containerWidth;
        canvas.height = graphHeight;

        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.drawImage(
            img,
            cropX,
            cropY,
            cropWidth,
            cropHeight,
            0,
            0,
            containerWidth,
            graphHeight,
          );
        }
        setError(false);
      } catch (err) {
        console.error("Failed to load cropped image:", err);
        setError(true);
      }
    };

    loadAndCropImage();
  }, [imageUrl, gridCoords, targetWidth]);

  if (!gridCoords || gridCoords.upper_left.x === 0) {
    return (
      <div
        className="bg-slate-50 dark:bg-slate-800 rounded flex items-center justify-center text-slate-400 text-sm border border-dashed border-slate-300 dark:border-slate-600"
        style={{ height: 200 }}
      >
        Select grid corners to see cropped graph
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="bg-slate-50 dark:bg-slate-800 rounded flex items-center justify-center text-red-400 text-sm border border-dashed border-red-300 dark:border-red-600"
        style={{ height: 200 }}
      >
        Failed to load image
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full overflow-hidden"
      style={{ height: 200 }}
    >
      <canvas
        ref={canvasRef}
        aria-label="Cropped view of the usage graph from screenshot"
        role="img"
        className="block w-full h-full rounded object-cover"
      />
    </div>
  );
};
