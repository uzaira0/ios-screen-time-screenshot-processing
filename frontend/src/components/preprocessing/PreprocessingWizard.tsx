import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";
import { STAGES } from "@/store/preprocessingStore";
import type { Stage } from "@/store/preprocessingStore";

const STAGE_LABELS: Record<Stage, string> = {
  device_detection: "Device Detection",
  cropping: "Cropping",
  phi_detection: "PHI Detection",
  phi_redaction: "PHI Redaction",
  ocr: "OCR",
};

const STAGE_NUMBERS: Record<Stage, number> = {
  device_detection: 1,
  cropping: 2,
  phi_detection: 3,
  phi_redaction: 4,
  ocr: 5,
};

export const PreprocessingWizard = () => {
  const activeStage = usePreprocessingStore((s) => s.activeStage);
  const setActiveStage = usePreprocessingStore((s) => s.setActiveStage);
  const summary = usePreprocessingStore((s) => s.summary);
  const screenshots = usePreprocessingStore((s) => s.screenshots);
  const getStageStatus = usePreprocessingStore((s) => s.getStageStatus);

  return (
    <div className="flex border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
      {STAGES.map((stage, idx) => {
        const isActive = activeStage === stage;
        const counts = summary
          ? summary[stage]
          : getStageStatus(stage);
        const total = summary?.total ?? screenshots.length;

        return (
          <button
            key={stage}
            onClick={() => setActiveStage(stage)}
            className={`flex-1 relative px-4 py-3 text-left transition-colors ${
              isActive
                ? "bg-white dark:bg-slate-800 border-b-2 border-primary-600"
                : "bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 border-b-2 border-transparent"
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span
                className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                  isActive
                    ? "bg-primary-600 text-white"
                    : counts.completed === total && total > 0
                      ? "bg-green-500 text-white"
                      : "bg-slate-300 text-slate-600 dark:bg-slate-600 dark:text-slate-300"
                }`}
              >
                {counts.completed === total && total > 0
                  ? "\u2713"
                  : STAGE_NUMBERS[stage]}
              </span>
              <span
                className={`text-sm font-medium ${
                  isActive ? "text-primary-700 dark:text-primary-400" : "text-slate-700 dark:text-slate-300"
                }`}
              >
                {STAGE_LABELS[stage]}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs ml-8">
              {counts.completed > 0 && (
                <span className="text-green-600">
                  {counts.completed} done
                </span>
              )}
              {counts.invalidated > 0 && (
                <span className="text-orange-500 font-medium">
                  {counts.invalidated} invalidated
                </span>
              )}
              {counts.pending > 0 && (
                <span className="text-slate-400">
                  {counts.pending} pending
                </span>
              )}
              {counts.running > 0 && (
                <span className="text-primary-500">
                  {counts.running} running
                </span>
              )}
              {counts.failed > 0 && (
                <span className="text-red-500">
                  {counts.failed} failed
                </span>
              )}
              {counts.exceptions > 0 && (
                <span className="text-yellow-600 font-medium">
                  {counts.exceptions} review
                </span>
              )}
            </div>
            {/* Connector line between steps */}
            {idx < STAGES.length - 1 && (
              <div className="absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-l-[6px] border-l-slate-200 dark:border-l-slate-700 translate-x-[6px] z-10" />
            )}
          </button>
        );
      })}
    </div>
  );
};
