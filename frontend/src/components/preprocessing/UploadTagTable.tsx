import { useId, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { UploadFileItem } from "@/store/preprocessingStore";

interface UploadTagTableProps {
  files: UploadFileItem[];
  groupId: string;
  imageType: "battery" | "screen_time";
  groupOptions?: string[];
  onFilesChange: (files: UploadFileItem[]) => void;
  onGroupIdChange: (groupId: string) => void;
  onImageTypeChange: (type: "battery" | "screen_time") => void;
}

// Grid column layout shared between header and body rows
const COLS = "1fr 160px 144px 40px";
const ROW_HEIGHT = 44; // px

export const UploadTagTable = ({
  files,
  groupId,
  imageType,
  groupOptions = [],
  onFilesChange,
  onGroupIdChange,
  onImageTypeChange,
}: UploadTagTableProps) => {
  const [regexInput, setRegexInput] = useState("");
  const [testInput, setTestInput] = useState("");
  const scrollParentRef = useRef<HTMLDivElement>(null);
  const datalistId = useId();

  const rowVirtualizer = useVirtualizer({
    count: files.length,
    getScrollElement: () => scrollParentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  // Compile regex from current input. Returns { re, error } — one of them is always null.
  const compileRegex = (raw: string): { re: RegExp | null; error: string | null } => {
    const trimmed = raw.trim();
    if (!trimmed) return { re: null, error: null };
    const pattern = trimmed.includes("(") ? trimmed : `(${trimmed})`;
    try {
      return { re: new RegExp(pattern), error: null };
    } catch (e) {
      return { re: null, error: (e as Error).message };
    }
  };

  const { re: liveRegex, error: regexError } = useMemo(() => compileRegex(regexInput), [regexInput]);

  const testPreview = useMemo(() => {
    if (!liveRegex || !testInput.trim()) return null;
    return testInput.match(liveRegex)?.[1] ?? null;
  }, [liveRegex, testInput]);

  const applyRegex = () => {
    if (!liveRegex) return;
    onFilesChange(
      files.map((item) => {
        const m = item.original_filepath.match(liveRegex);
        return m?.[1] ? { ...item, participant_id: m[1] } : item;
      }),
    );
  };

  const updateItem = (index: number, field: keyof UploadFileItem, value: string) => {
    const updated = [...files];
    updated[index] = { ...updated[index]!, [field]: value };
    onFilesChange(updated);
  };

  const removeItem = (index: number) => {
    onFilesChange(files.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      {/* Group-level fields */}
      <div className="flex flex-wrap items-center gap-4 p-3 bg-slate-50 dark:bg-slate-700/50 rounded-lg border dark:border-slate-700">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Group ID:</label>
          <div className="flex flex-col">
            <input
              type="text"
              list={datalistId}
              value={groupId}
              onChange={(e) => onGroupIdChange(e.target.value)}
              className="text-sm border border-slate-300 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded-md px-3 py-1.5 w-52"
              placeholder="Enter or select a group"
            />
            {groupOptions.length > 0 && (
              <datalist id={datalistId}>
                {groupOptions.map((g) => <option key={g} value={g} />)}
              </datalist>
            )}
            {groupOptions.length > 0 && (
              <span className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">Enter group name or select a previous group</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Type:</label>
          <select
            value={imageType}
            onChange={(e) => onImageTypeChange(e.target.value as "battery" | "screen_time")}
            className="text-sm border border-slate-300 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded-md px-2 py-1.5"
          >
            <option value="screen_time">Screen Time</option>
            <option value="battery">Battery</option>
          </select>
        </div>
        <span className="text-sm text-slate-500 dark:text-slate-400 ml-auto">
          {files.length} file{files.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Participant ID Regex */}
      <div className="space-y-2 p-3 bg-slate-50 dark:bg-slate-700/50 rounded-lg border dark:border-slate-700">
        {/* Regex input row */}
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-slate-700 dark:text-slate-300 whitespace-nowrap">
            Participant ID Regex:
          </label>
          <input
            type="text"
            value={regexInput}
            onChange={(e) => setRegexInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") applyRegex(); }}
            className={`text-sm border rounded-md px-3 py-1.5 flex-1 min-w-[200px] font-mono ${
              regexError
                ? "border-red-400 bg-red-50 dark:border-red-600 dark:bg-red-900/20 dark:text-slate-200"
                : "border-slate-300 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
            }`}
            placeholder="e.g. (P\d{3})"
          />
          <button
            type="button"
            onClick={applyRegex}
            disabled={!liveRegex}
            className="px-3 py-1.5 text-sm font-medium text-primary-700 bg-primary-50 border border-primary-200 rounded-md hover:bg-primary-100 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Apply
          </button>
        </div>

        {/* Error */}
        {regexError && (
          <p className="text-xs text-red-600 dark:text-red-400">Invalid regex: {regexError}</p>
        )}

        {/* Test box — only shown once the user has typed a valid regex */}
        {liveRegex && (
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
              Test path:
            </label>
            <input
              type="text"
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              className="text-xs border border-slate-300 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded-md px-3 py-1.5 flex-1 font-mono"
              placeholder="paste a file path to preview the match"
            />
            {testInput.trim() && (
              <span className={`text-xs font-mono px-2 py-1 rounded whitespace-nowrap ${
                testPreview
                  ? "bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-700"
                  : "bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-700"
              }`}>
                {testPreview ? `→ "${testPreview}"` : "no match"}
              </span>
            )}
          </div>
        )}
      </div>

      {/* File list — virtualized so large folders don't freeze the browser */}
      <div className="border dark:border-slate-700 rounded-lg overflow-hidden text-sm">
        {/* Header */}
        <div
          className="grid text-xs font-medium text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-800 border-b dark:border-slate-700 px-3 py-2"
          style={{ gridTemplateColumns: COLS }}
        >
          <span>Filename</span>
          <span>Participant ID</span>
          <span>Date</span>
          <span />
        </div>
        {/* Virtualized rows */}
        <div ref={scrollParentRef} className="overflow-y-auto" style={{ maxHeight: 384 }}>
          <div style={{ height: rowVirtualizer.getTotalSize(), position: "relative" }}>
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const i = virtualRow.index;
              const item = files[i]!;
              return (
                <div
                  key={i}
                  className="grid items-center border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 px-3"
                  style={{
                    gridTemplateColumns: COLS,
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: `${ROW_HEIGHT}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <div className="pr-2 text-xs text-slate-600 dark:text-slate-400 truncate min-w-0" title={item.original_filepath}>
                    {item.filename}
                  </div>
                  <div className="pr-2">
                    <input
                      type="text"
                      value={item.participant_id}
                      onChange={(e) => updateItem(i, "participant_id", e.target.value)}
                      className="w-full text-xs border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded px-2 py-1"
                    />
                  </div>
                  <div className="pr-2">
                    <input
                      type="date"
                      value={item.screenshot_date}
                      onChange={(e) => updateItem(i, "screenshot_date", e.target.value)}
                      className="w-full text-xs border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded px-2 py-1"
                    />
                  </div>
                  <div>
                    <button
                      onClick={() => removeItem(i)}
                      className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 text-sm leading-none"
                      title="Remove file"
                      aria-label={`Remove ${item.filename}`}
                    >
                      &times;
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
