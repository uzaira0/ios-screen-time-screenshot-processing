/**
 * WASM Home Page
 *
 * Main page for WASM mode - handles screenshot upload, processing,
 * and management entirely in the browser.
 */

import React, { useState, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { Link } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { ExportDialog } from "@/components/pwa/ExportDialog";
import { KeyboardShortcuts } from "@/components/pwa/KeyboardShortcuts";
import { GroupList } from "@/components/groups/GroupList";
import { useServices } from "@/hooks/useServices";
import toast from "react-hot-toast";
import { IMAGE_TYPES } from "@/types";
import type { ImageType } from "@/types";

interface Screenshot {
  id: number;
  filename: string;
  uploadedAt: Date;
  status: "pending" | "processing" | "completed" | "error";
  thumbnailUrl?: string;
}

export const WasmHomePage: React.FC = () => {
  const { screenshot } = useServices();
  const [screenshots, setScreenshots] = useState<Screenshot[]>([]);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [isKeyboardShortcutsOpen, setIsKeyboardShortcutsOpen] = useState(false);
  const [selectedScreenshot, setSelectedScreenshot] = useState<
    number | undefined
  >();

  useEffect(() => {
    loadScreenshots();

    // Cleanup blob URLs on unmount
    return () => {
      screenshots.forEach((s) => {
        if (s.thumbnailUrl && s.thumbnailUrl.startsWith("blob:")) {
          URL.revokeObjectURL(s.thumbnailUrl);
        }
      });
    };
  }, []);

  const loadScreenshots = async () => {
    try {
      // Use the correct interface method
      const data = await screenshot.getAll();

      // Map to our local Screenshot interface and load thumbnail URLs
      const mapped: Screenshot[] = await Promise.all(
        data.map(async (s) => {
          let thumbnailUrl: string | undefined;

          try {
            // getImageUrl always returns Promise<string> now
            thumbnailUrl = await screenshot.getImageUrl(s.id);
          } catch (error) {
            console.error(`Failed to load thumbnail for ${s.id}:`, error);
          }

          return {
            id: s.id,
            filename: s.file_path.split("/").pop() || `screenshot-${s.id}`,
            uploadedAt: new Date(s.uploaded_at),
            status:
              s.annotation_status === "pending" &&
              s.processing_status === "processing"
                ? "processing"
                : s.annotation_status === "pending"
                  ? "pending"
                  : s.annotation_status === "annotated" ||
                      s.annotation_status === "verified"
                    ? "completed"
                    : "error",
            thumbnailUrl,
          };
        }),
      );

      setScreenshots(mapped);
    } catch (error) {
      console.error("Failed to load screenshots:", error);
      toast.error("Failed to load screenshots");
    }
  };

  const onDrop = async (acceptedFiles: File[]) => {
    console.log(`Starting upload of ${acceptedFiles.length} files`);

    for (const file of acceptedFiles) {
      try {
        console.log(`Uploading file: ${file.name}`);
        toast.loading(`Uploading ${file.name}...`, { id: file.name });

        // Detect image type from filename
        const imageType: ImageType = file.name.toLowerCase().includes("battery")
          ? IMAGE_TYPES.BATTERY
          : IMAGE_TYPES.SCREEN_TIME;

        const uploadedScreenshot = await screenshot.upload(file, imageType);
        console.log(
          `Upload successful for ${file.name}, ID: ${uploadedScreenshot.id}`,
        );

        toast.success(`${file.name} uploaded successfully!`, { id: file.name });
      } catch (error) {
        console.error(`Upload failed for ${file.name}:`, error);
        toast.error(`Failed to upload ${file.name}`, { id: file.name });
      }
    }

    console.log(`Upload loop complete, reloading screenshots`);
    // Reload all screenshots once after the loop completes
    await loadScreenshots();
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/*": [".png", ".jpg", ".jpeg", ".webp"],
    },
    multiple: true,
  });

  const handleExport = (screenshotId?: number) => {
    setSelectedScreenshot(screenshotId);
    setIsExportOpen(true);
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const modKey = isMac ? e.metaKey : e.ctrlKey;

      if (modKey && e.key === "k") {
        e.preventDefault();
        setIsKeyboardShortcutsOpen(true);
      }
      if (modKey && e.key === "e") {
        e.preventDefault();
        handleExport();
      }
    };

    window.addEventListener("keydown", handleKeyPress);
    return () => window.removeEventListener("keydown", handleKeyPress);
  }, []);

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              iOS Screen Time
            </h1>
            <p className="text-gray-600 mt-1">
              Process iOS battery and screen time screenshots locally
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setIsKeyboardShortcutsOpen(true)}
              className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              title="Show keyboard shortcuts (Ctrl+K)"
            >
              ⌨️ Shortcuts
            </button>
            <button
              onClick={() => handleExport()}
              className="px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
              title="Export data (Ctrl+E)"
            >
              📤 Export
            </button>
          </div>
        </div>

        {/* Upload Area */}
        <div
          {...getRootProps()}
          className={`
            border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors
            ${
              isDragActive
                ? "border-blue-500 bg-blue-50"
                : "border-gray-300 bg-gray-50 hover:border-gray-400"
            }
          `}
        >
          <input {...getInputProps()} />
          <div className="text-6xl mb-4">📸</div>
          {isDragActive ? (
            <p className="text-lg text-blue-600 font-medium">
              Drop screenshots here...
            </p>
          ) : (
            <>
              <p className="text-lg text-gray-700 font-medium mb-2">
                Drag & drop screenshots here, or click to select
              </p>
              <p className="text-sm text-gray-500">
                Supports PNG, JPG, JPEG, and WebP images
              </p>
            </>
          )}
        </div>

        {/* Groups Section */}
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold text-gray-900">Groups</h2>
            <p className="text-sm text-gray-500">
              Click a group to start annotating
            </p>
          </div>
          <GroupList />
        </div>

        {/* Info Banner */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-start gap-2">
            <svg
              className="w-5 h-5 text-blue-600 mt-0.5"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                clipRule="evenodd"
              />
            </svg>
            <div className="text-sm text-blue-900">
              <p className="font-medium mb-1">Local Processing Mode</p>
              <p>
                All processing happens in your browser. Your data never leaves
                your device. Screenshots can be uploaded via API or manually
                below.
              </p>
            </div>
          </div>
        </div>

        {/* Upload Stats */}
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Upload Queue
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-gray-900">
                {screenshots.length}
              </div>
              <div className="text-sm text-gray-600">Total Uploaded</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-yellow-600">
                {screenshots.filter((s) => s.status === "pending").length}
              </div>
              <div className="text-sm text-gray-600">Pending Annotation</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">
                {screenshots.filter((s) => s.status === "completed").length}
              </div>
              <div className="text-sm text-gray-600">Preprocessed</div>
            </div>
          </div>
          {screenshots.filter((s) => s.status === "pending").length > 0 && (
            <div className="mt-4 text-center">
              <Link
                to="/annotate"
                className="inline-block px-6 py-3 bg-primary-600 hover:bg-primary-700 text-white rounded-lg font-medium transition-colors"
              >
                Start Annotating →
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* Dialogs */}
      <ExportDialog
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
        screenshotId={selectedScreenshot}
      />

      <KeyboardShortcuts
        isOpen={isKeyboardShortcutsOpen}
        onClose={() => setIsKeyboardShortcutsOpen(false)}
      />
    </Layout>
  );
};
