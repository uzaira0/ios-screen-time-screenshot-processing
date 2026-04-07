interface PreprocessingSummaryProps {
  processingMetadata?: Record<string, unknown> | null | undefined;
  onEditPHI?: () => void;
  onEditCrop?: () => void;
}

/** Extract the current event result for a stage from processing_metadata */
function getStageResult(processingMetadata: Record<string, unknown> | null | undefined, stage: string): Record<string, unknown> | null {
  const pp = processingMetadata?.preprocessing as Record<string, unknown> | undefined;
  if (!pp) return null;

  // Try event-based lookup first (works for both WASM and server)
  const currentEvents = pp.current_events as Record<string, number | null> | undefined;
  const events = pp.events as Array<{ event_id: number; result: Record<string, unknown> }> | undefined;
  if (currentEvents && events) {
    const eid = currentEvents[stage];
    if (eid != null) {
      const event = events.find((e) => e.event_id === eid);
      if (event) return event.result;
    }
  }

  // Fallback: server mode may also store as top-level keys (legacy PreprocessingDetailsResponse shape)
  const direct = pp[stage] as Record<string, unknown> | undefined;
  if (direct) return direct;

  return null;
}

export const PreprocessingSummary = ({
  processingMetadata,
  onEditPHI,
  onEditCrop,
}: PreprocessingSummaryProps) => {
  const pp = (processingMetadata as Record<string, unknown>)?.preprocessing as Record<string, unknown> | undefined;
  if (!pp) return null;

  const dd = getStageResult(processingMetadata, "device_detection");
  const cr = getStageResult(processingMetadata, "cropping");
  const pd = getStageResult(processingMetadata, "phi_detection");
  const pr = getStageResult(processingMetadata, "phi_redaction");

  const deviceCategory = dd?.device_category as string | undefined;
  const deviceModel = dd?.device_model as string | undefined;
  const confidence = dd?.confidence as number | undefined;
  const wasCropped = cr?.was_cropped === true || cr?.wasCropped === true;
  const phiDetected = pd?.phi_detected === true;
  const regionsCount = (pd?.regions_count as number) ?? (pd?.phi_entities as unknown[] | undefined)?.length ?? 0;
  const wasRedacted = pr?.redacted === true;
  const regionsRedacted = pr?.regions_redacted as number | undefined;
  const redactionMethod = pr?.method as string | undefined;

  // Nothing to show
  if (!dd && !cr && !pd && !pr) return null;

  return (
    <div className="border-b border-slate-100 dark:border-slate-700 pb-2">
      <div className="text-xs text-slate-500 mb-1">Preprocessing</div>
      <div className="flex flex-wrap gap-1.5">
        {dd && deviceCategory && (
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
              deviceCategory === "ipad"
                ? "bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400"
                : deviceCategory === "iphone"
                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                  : "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400"
            }`}
            title={`Device: ${deviceModel || deviceCategory}${confidence != null ? ` (${Math.round(confidence * 100)}%)` : ""}`}
          >
            {deviceCategory}
          </span>
        )}
        {wasCropped && (
          onEditCrop ? (
            <button
              onClick={onEditCrop}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 hover:ring-2 hover:ring-purple-300 hover:ring-offset-1 transition-all cursor-pointer"
              title="iPad sidebar was cropped — click to adjust"
            >
              Cropped <span className="opacity-60">&#9998;</span>
            </button>
          ) : (
            <span
              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400"
              title="iPad sidebar was cropped"
            >
              Cropped
            </span>
          )
        )}
        {pd && (
          onEditPHI ? (
            <button
              onClick={onEditPHI}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium hover:ring-2 hover:ring-offset-1 transition-all cursor-pointer ${
                phiDetected
                  ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 hover:ring-red-300"
                  : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 hover:ring-green-300"
              }`}
              title={
                phiDetected
                  ? `PHI detected: ${regionsCount} region(s) — click to edit`
                  : "No PHI detected — click to review"
              }
            >
              {phiDetected ? `PHI: ${regionsCount}` : "No PHI"}
              <span className="opacity-60">&#9998;</span>
            </button>
          ) : (
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                phiDetected
                  ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                  : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
              }`}
              title={
                phiDetected
                  ? `PHI detected: ${regionsCount} region(s)`
                  : "No PHI detected"
              }
            >
              {phiDetected ? `PHI: ${regionsCount}` : "No PHI"}
            </span>
          )
        )}
        {wasRedacted && (
          onEditPHI ? (
            <button
              onClick={onEditPHI}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 hover:ring-2 hover:ring-orange-300 hover:ring-offset-1 transition-all cursor-pointer"
              title={`${regionsRedacted ?? "?"} region(s) redacted via ${redactionMethod ?? "?"} — click to edit`}
            >
              Redacted <span className="opacity-60">&#9998;</span>
            </button>
          ) : (
            <span
              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400"
              title={`${regionsRedacted ?? "?"} region(s) redacted via ${redactionMethod ?? "?"}`}
            >
              Redacted
            </span>
          )
        )}
      </div>
    </div>
  );
};
