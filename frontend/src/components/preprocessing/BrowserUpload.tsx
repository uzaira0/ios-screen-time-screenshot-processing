import { useCallback, useMemo } from "react";
import { usePreprocessingStore } from "@/hooks/usePreprocessingWithDI";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";
import type { UploadFileItem } from "@/store/preprocessingStore";
import { UploadDropZone } from "./UploadDropZone";
import { UploadTagTable } from "./UploadTagTable";
import { UploadProgressBar } from "./UploadProgressBar";

export const BrowserUpload = () => {
  const uploadFiles = usePreprocessingStore((s) => s.uploadFiles);
  const setUploadFiles = usePreprocessingStore((s) => s.setUploadFiles);
  const uploadGroupId = usePreprocessingStore((s) => s.uploadGroupId);
  const setUploadGroupId = usePreprocessingStore((s) => s.setUploadGroupId);
  const uploadImageType = usePreprocessingStore((s) => s.uploadImageType);
  const setUploadImageType = usePreprocessingStore((s) => s.setUploadImageType);
  const isUploading = usePreprocessingStore((s) => s.isUploading);
  const uploadProgress = usePreprocessingStore((s) => s.uploadProgress);
  const uploadErrors = usePreprocessingStore((s) => s.uploadErrors);
  const startBrowserUpload = usePreprocessingStore((s) => s.startBrowserUpload);
  const cancelUpload = usePreprocessingStore((s) => s.cancelUpload);
  const setSelectedGroupId = usePreprocessingStore((s) => s.setSelectedGroupId);

  const { confirm, ConfirmDialog } = useConfirmDialog();

  const canUpload = uploadFiles.length > 0 && uploadGroupId.trim().length > 0 && !isUploading;

  // Append new files to existing list (dedup by original_filepath)
  const appendFiles = useCallback(
    (newFiles: UploadFileItem[]) => {
      const existingPaths = new Set(uploadFiles.map((f) => f.original_filepath));
      const unique = newFiles.filter((f) => !existingPaths.has(f.original_filepath));
      setUploadFiles([...uploadFiles, ...unique]);
    },
    [uploadFiles, setUploadFiles],
  );

  const groups = usePreprocessingStore((s) => s.groups);
  const groupIds = useMemo(() => groups.map((g) => g.id), [groups]);
  const setPageMode = usePreprocessingStore((s) => s.setPageMode);
  const resetUploadResult = usePreprocessingStore((s) => s.resetUploadResult);

  const clearUpload = () => {
    resetUploadResult();
  };

  // Step 1: Drop zone (no files yet, no completed upload)
  if (uploadFiles.length === 0 && !isUploading && !uploadProgress) {
    return (
      <div className="space-y-4">
        <UploadDropZone onFilesSelected={setUploadFiles} />
      </div>
    );
  }

  // Step 3: Uploading in progress
  if (isUploading && uploadProgress) {
    return (
      <div className="space-y-4">
        <UploadProgressBar
          completed={uploadProgress.completed}
          total={uploadProgress.total}
          errors={uploadErrors}
        />
        <button
          onClick={cancelUpload}
          className="px-4 py-2 text-sm font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md hover:bg-red-100 dark:hover:bg-red-900/30"
        >
          Cancel Upload
        </button>
      </div>
    );
  }

  // Step 4: Upload finished — show persistent result until user acts
  if (!isUploading && uploadFiles.length === 0 && uploadProgress) {
    const succeeded = uploadProgress.completed;
    const failed = uploadErrors.length;
    const allOk = failed === 0;
    return (
      <div className="space-y-4">
        {/* Result banner */}
        <div className={`p-4 rounded-lg border ${allOk ? "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700" : "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-700"}`}>
          <p className={`text-sm font-medium ${allOk ? "text-green-800 dark:text-green-300" : "text-yellow-800 dark:text-yellow-300"}`}>
            {allOk
              ? `${succeeded} screenshot${succeeded !== 1 ? "s" : ""} uploaded successfully`
              : `${succeeded} uploaded, ${failed} failed`}
          </p>
          {failed > 0 && (
            <ul className="mt-2 text-xs text-yellow-700 dark:text-yellow-400 space-y-0.5 max-h-32 overflow-y-auto">
              {uploadErrors.map((err, i) => <li key={i}>{err}</li>)}
            </ul>
          )}
        </div>
        {/* Progress bar showing final state */}
        <UploadProgressBar
          completed={uploadProgress.completed}
          total={uploadProgress.total}
          errors={[]}
        />
        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={clearUpload}
            className="px-4 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 dark:text-slate-200"
          >
            Upload More
          </button>
          <button
            onClick={() => {
              if (uploadGroupId) setSelectedGroupId(uploadGroupId);
              setPageMode("pipeline");
            }}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700"
          >
            View in Pipeline →
          </button>
        </div>
      </div>
    );
  }

  // Step 2: Tag table with ability to add more folders
  return (
    <div className="space-y-4">
      <UploadTagTable
        files={uploadFiles}
        groupId={uploadGroupId}
        imageType={uploadImageType}
        groupOptions={groupIds}
        onFilesChange={setUploadFiles}
        onGroupIdChange={setUploadGroupId}
        onImageTypeChange={setUploadImageType}
      />
      {/* Compact drop zone for adding more folders */}
      <UploadDropZone onFilesSelected={appendFiles} compact />
      <div className="flex items-center justify-between">
        <button
          onClick={async () => {
            if (uploadFiles.length > 0) {
              const ok = await confirm({ title: "Clear Files", message: `Clear all ${uploadFiles.length} selected files?`, confirmLabel: "Clear All", variant: "danger" });
              if (ok) setUploadFiles([]);
            }
          }}
          className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 focus-ring"
        >
          Clear
        </button>
        <button
          onClick={startBrowserUpload}
          disabled={!canUpload}
          className="px-6 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed focus-ring"
        >
          Upload {uploadFiles.length} File{uploadFiles.length !== 1 ? "s" : ""}
        </button>
      </div>
      {ConfirmDialog}
    </div>
  );
};
