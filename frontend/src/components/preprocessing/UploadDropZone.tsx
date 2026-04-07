import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import type { UploadFileItem } from "@/store/preprocessingStore";
import { parseRelativePath, isImageFile } from "@/utils/filePathParser";
import { FolderStructureHint } from "@/components/common/FolderStructureHint";

interface UploadDropZoneProps {
  onFilesSelected: (files: UploadFileItem[]) => void;
  compact?: boolean;
}

export const UploadDropZone = ({ onFilesSelected, compact }: UploadDropZoneProps) => {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const imageFiles = acceptedFiles.filter(isImageFile);
      const items: UploadFileItem[] = imageFiles.map((file) => {
        const parsed = parseRelativePath(file);
        return {
          file,
          participant_id: parsed.participant_id,
          filename: parsed.filename,
          original_filepath: parsed.original_filepath,
          screenshot_date: parsed.screenshot_date,
        };
      });
      onFilesSelected(items);
    },
    [onFilesSelected],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: { "image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"] },
    maxSize: 25 * 1024 * 1024, // 25 MB per file
    multiple: true,
    noClick: true,
  });

  // Compact version: inline bar for adding more folders to an existing selection
  if (compact) {
    return (
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-3 text-center transition-colors ${
          isDragActive ? "border-primary-400 bg-primary-50 dark:bg-primary-900/20" : "border-slate-200 dark:border-slate-600 hover:border-slate-300 dark:hover:border-slate-500"
        }`}
      >
        <input {...getInputProps()} />
        <input {...getInputProps()} webkitdirectory="" directory="" style={{ display: "none" }} id="folder-input-add" />
        <div className="flex items-center justify-center gap-3">
          <span className="text-sm text-slate-400 dark:text-slate-500">
            {isDragActive ? "Drop to add..." : "Add more files or folders"}
          </span>
          <button
            type="button"
            className="px-3 py-1 text-xs bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-600 dark:text-slate-200 focus-ring"
            onClick={open}
          >
            + Files
          </button>
          <button
            type="button"
            className="px-3 py-1 text-xs bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-600 dark:text-slate-200 focus-ring"
            onClick={(e) => {
              e.stopPropagation();
              document.getElementById("folder-input-add")?.click();
            }}
          >
            + Folder
          </button>
        </div>
      </div>
    );
  }

  // Full-size drop zone for initial selection
  return (
    <div
      {...getRootProps()}
      className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
        isDragActive ? "border-primary-400 bg-primary-50 dark:bg-primary-900/20" : "border-slate-300 dark:border-slate-600 hover:border-slate-400 dark:hover:border-slate-500"
      }`}
    >
      <input {...getInputProps()} />
      <input {...getInputProps()} webkitdirectory="" directory="" style={{ display: "none" }} id="folder-input" />
      <div className="space-y-3">
        <div className="text-slate-400">
          {isDragActive ? (
            <svg className="w-10 h-10 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
            </svg>
          ) : (
            <svg className="w-10 h-10 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          )}
        </div>
        <p className="text-slate-600 dark:text-slate-300 font-medium">
          {isDragActive ? "Drop files here..." : "Drop screenshot files or folders here"}
        </p>
        <p className="text-sm text-slate-400 dark:text-slate-500">
          PNG/JPEG images
        </p>
        <FolderStructureHint />
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            type="button"
            className="px-4 py-2 text-sm bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-600 dark:text-slate-200 focus-ring"
            onClick={open}
          >
            Select Files
          </button>
          <button
            type="button"
            className="px-4 py-2 text-sm bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-600 dark:text-slate-200 focus-ring"
            onClick={(e) => {
              e.stopPropagation();
              document.getElementById("folder-input")?.click();
            }}
          >
            Select Folder
          </button>
        </div>
      </div>
    </div>
  );
};
