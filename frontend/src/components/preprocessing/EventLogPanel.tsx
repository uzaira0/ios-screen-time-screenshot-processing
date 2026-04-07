import { useState } from "react";
import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => { /* clipboard denied or unavailable */ });
  };
  return (
    <button
      onClick={handleCopy}
      className="px-1.5 py-0.5 text-[10px] rounded bg-slate-200 dark:bg-slate-600 text-slate-500 dark:text-slate-400 hover:bg-slate-300 dark:hover:bg-slate-500 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
      title="Copy to clipboard"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

const STAGE_LABELS: Record<string, string> = {
  device_detection: "Device Detection",
  cropping: "Cropping",
  phi_detection: "PHI Detection",
  phi_redaction: "PHI Redaction",
};

export const EventLogPanel = () => {
  const eventLog = usePreprocessingStore((s) => s.eventLog);
  const selectedScreenshotId = usePreprocessingStore((s) => s.selectedScreenshotId);
  const clearEventLog = usePreprocessingStore((s) => s.clearEventLog);

  if (!eventLog || !selectedScreenshotId) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-white dark:bg-slate-800 shadow-xl border-l border-slate-200 dark:border-slate-700 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-700/50">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Event Log - Screenshot #{selectedScreenshotId}
        </h3>
        <button
          onClick={clearEventLog}
          className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-lg leading-none"
          aria-label="Close event log"
        >
          &times;
        </button>
      </div>

      {/* Stage status summary */}
      <div className="px-4 py-2 border-b border-slate-100 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-700/30">
        <div className="flex flex-wrap gap-2">
          {Object.entries(eventLog.stage_status).map(([stage, status]) => (
            <div key={stage} className="flex items-center gap-1">
              <span className="text-xs text-slate-500">
                {STAGE_LABELS[stage] ?? stage}:
              </span>
              <span
                className={`text-xs font-medium ${
                  status === "completed"
                    ? "text-green-600"
                    : status === "invalidated"
                      ? "text-orange-500"
                      : status === "failed"
                        ? "text-red-500"
                        : status === "running"
                          ? "text-primary-500"
                          : "text-slate-400"
                }`}
              >
                {status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Events list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {eventLog.events.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-8">
            No events recorded yet
          </p>
        ) : (
          [...eventLog.events].reverse().map((event) => {
            const isCurrent = eventLog.current_events[event.stage] === event.event_id;
            const isError = "error" in event.result;

            return (
              <div
                key={event.event_id}
                className={`rounded-lg border p-3 text-xs ${
                  isCurrent
                    ? "border-primary-200 bg-primary-50/30 dark:border-primary-700 dark:bg-primary-900/20"
                    : isError
                      ? "border-red-200 bg-red-50/30 dark:border-red-700 dark:bg-red-900/20"
                      : "border-slate-100 bg-white opacity-60 dark:border-slate-700 dark:bg-slate-800"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-700 dark:text-slate-300">
                      #{event.event_id}
                    </span>
                    {event.source && (
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          event.source === "auto"
                            ? "bg-primary-100 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400"
                            : "bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400"
                        }`}
                      >
                        {event.source}
                      </span>
                    )}
                    <span className="text-slate-500">
                      {STAGE_LABELS[event.stage] ?? event.stage}
                    </span>
                    {isCurrent && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400">
                        current
                      </span>
                    )}
                  </div>
                  {event.supersedes && (
                    <span className="text-slate-400">
                      replaces #{event.supersedes}
                    </span>
                  )}
                </div>
                <div className="text-slate-400 mb-1">
                  {new Date(event.timestamp).toLocaleString()}
                </div>
                {/* Result summary */}
                <div className="mt-1 text-slate-600 dark:text-slate-400">
                  {isError ? (
                    <div className="flex items-start gap-1">
                      <span className="text-red-600 flex-1">
                        Error: {event.result.error as string}
                      </span>
                      <CopyButton text={event.result.error as string} />
                    </div>
                  ) : (
                    <div className="relative group">
                      <pre className="whitespace-pre-wrap break-all text-[10px] bg-slate-50 dark:bg-slate-700/50 rounded p-1.5 max-h-24 overflow-y-auto">
                        {JSON.stringify(event.result, null, 1)}
                      </pre>
                      <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <CopyButton text={JSON.stringify(event.result, null, 2)} />
                      </div>
                    </div>
                  )}
                </div>
                {event.output_file && (
                  <div className="mt-1 text-slate-400 truncate" title={event.output_file}>
                    Output: {event.output_file.split("/").pop()}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between">
        {eventLog.base_file_path ? (
          <span className="text-xs text-slate-400 truncate mr-2">
            Base: {eventLog.base_file_path.split("/").pop()}
          </span>
        ) : <span />}
        <button
          onClick={() => {
            const json = JSON.stringify(eventLog, null, 2);
            const blob = new Blob([json], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `event-log-${selectedScreenshotId}.json`;
            a.click();
            URL.revokeObjectURL(url);
          }}
          className="text-xs text-slate-500 dark:text-slate-400 hover:text-primary-600 dark:hover:text-primary-400"
          title="Download full event log as JSON"
        >
          Export JSON
        </button>
      </div>
    </div>
  );
};
