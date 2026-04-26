import { memo, useMemo } from "react";
import type { HourlyData, Consensus } from "@/types";
import clsx from "clsx";

interface HourlyUsageEditorProps {
  data: HourlyData;
  onChange: (hour: number, value: number) => void;
  consensus?: Consensus;
  readOnly?: boolean;
  title?: string;
}

const HourlyUsageEditorInner = ({
  data,
  onChange,
  consensus,
  readOnly = false,
}: HourlyUsageEditorProps) => {
  const handleChange = (hour: number, delta: number) => {
    const currentValue = data[hour] || 0;
    const newValue = Math.max(0, Math.min(60, currentValue + delta));
    onChange(hour, newValue);
  };

  const handleInputChange = (hour: number, value: string) => {
    const numValue = parseInt(value) || 0;
    if (numValue < 0 || numValue > 60) return;
    onChange(hour, numValue);
  };

  // Build a Map from hour -> disagreement for O(1) lookups instead of find() per hour
  const disagreementMap = useMemo(() => {
    if (!consensus) return null;
    const map = new Map<number, { consensus_value: number }>();
    for (const d of consensus.disagreements) {
      map.set(d.hour, d);
    }
    return map;
  }, [consensus]);

  const getDisagreementLevel = (
    hour: number,
  ): "none" | "minor" | "major" | null => {
    if (!disagreementMap) return null;
    const disagreement = disagreementMap.get(hour);
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
      "w-full text-center text-sm font-medium border rounded-md focus:outline-none focus:ring-2 transition-all py-1",
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
    <div className="w-full" data-testid="hourly-editor">
      {/* Bar Graph - EXACTLY 24 columns */}
      <div
        className="relative bg-white rounded-lg overflow-hidden border border-slate-200"
        style={{ height: graphHeight }}
      >
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
                className="flex flex-col h-full justify-end items-center border-r border-slate-200 last:border-r-0"
              >
                {/* Bar */}
                <div
                  className="w-4/5 bg-blue-500 border-t border-blue-600/30 transition-all duration-300 rounded-t-md"
                  style={{
                    height: `${heightPercentage}%`,
                    minHeight: value > 0 ? "2px" : "0",
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* Controls grid - EXACTLY 24 columns to match bar graph above */}
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
                inputMode="numeric"
                pattern="[0-9]*"
                value={value}
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

export const HourlyUsageEditor = memo(HourlyUsageEditorInner);
