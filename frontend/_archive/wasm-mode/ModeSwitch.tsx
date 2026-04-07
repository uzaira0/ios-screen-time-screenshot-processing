import React, { useState } from "react";
import { useMode } from "@/hooks/useMode";
import type { AppMode } from "@/config/environment";
import toast from "react-hot-toast";

interface ModeSwitchProps {
  className?: string;
}

interface ModeInfo {
  title: string;
  description: string;
  pros: string[];
  cons: string[];
  icon: string;
}

const MODE_INFO: Record<AppMode, ModeInfo> = {
  server: {
    title: "Server Mode",
    description: "Process screenshots using the backend server",
    pros: [
      "Faster processing with server GPU acceleration",
      "Centralized data storage and management",
      "Multi-user collaboration and consensus features",
      "Real-time updates via WebSocket",
    ],
    cons: [
      "Requires internet connection",
      "Requires backend server to be running",
      "Data stored on server",
    ],
    icon: "🖥️",
  },
  wasm: {
    title: "Local Mode (WASM)",
    description: "Process screenshots entirely in your browser",
    pros: [
      "100% offline - works without internet",
      "Complete privacy - data never leaves your device",
      "No server required - fully self-contained",
      "Installable as a Progressive Web App",
    ],
    cons: [
      "Slower processing (browser-based)",
      "Uses more memory",
      "No collaboration features",
      "Data stored locally only",
    ],
    icon: "💻",
  },
};

export const ModeSwitch: React.FC<ModeSwitchProps> = ({ className = "" }) => {
  const { mode: currentMode, switchMode, config } = useMode();
  const [showModal, setShowModal] = useState(false);
  const [selectedMode, setSelectedMode] = useState<AppMode | null>(null);

  const handleModeSelect = (mode: AppMode) => {
    if (mode === currentMode) {
      return;
    }

    // Check if the mode is available
    if (mode === "server" && !config.serverAvailable) {
      toast.error("Server mode is not available. No backend configured.");
      return;
    }

    if (mode === "wasm" && !config.wasmAvailable) {
      toast.error("Your browser does not support WebAssembly");
      return;
    }

    setSelectedMode(mode);
    setShowModal(true);
  };

  const confirmModeChange = () => {
    if (!selectedMode) return;

    try {
      switchMode(selectedMode);
      setShowModal(false);
      toast.success(`Switching to ${MODE_INFO[selectedMode].title}...`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to switch mode",
      );
      setShowModal(false);
    }
  };

  const cancelModeChange = () => {
    setSelectedMode(null);
    setShowModal(false);
  };

  return (
    <>
      <div className={`mode-switch ${className}`}>
        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium text-gray-700">
            Processing Mode
          </label>
          <div className="grid grid-cols-2 gap-2">
            {(["server", "wasm"] as AppMode[]).map((mode) => {
              const isDisabled =
                (mode === "server" && !config.serverAvailable) ||
                (mode === "wasm" && !config.wasmAvailable);

              return (
                <button
                  key={mode}
                  onClick={() => handleModeSelect(mode)}
                  disabled={isDisabled}
                  className={`
                    flex flex-col items-center justify-center p-4 rounded-lg border-2 transition-all
                    ${
                      currentMode === mode
                        ? "border-blue-500 bg-blue-50"
                        : isDisabled
                          ? "border-gray-200 bg-gray-100 cursor-not-allowed opacity-50"
                          : "border-gray-200 bg-white hover:border-gray-300"
                    }
                  `}
                >
                  <span className="text-3xl mb-2">{MODE_INFO[mode].icon}</span>
                  <span className="font-medium text-sm">
                    {MODE_INFO[mode].title}
                  </span>
                  <span className="text-xs text-gray-500 mt-1 text-center">
                    {mode === "server"
                      ? config.serverAvailable
                        ? "Requires backend"
                        : "Not available"
                      : "100% offline"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {showModal && selectedMode && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={cancelModeChange}
        >
          <div
            className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <span className="text-4xl">{MODE_INFO[selectedMode].icon}</span>
                <div>
                  <h2 className="text-2xl font-bold text-gray-900">
                    Switch to {MODE_INFO[selectedMode].title}?
                  </h2>
                  <p className="text-gray-600">
                    {MODE_INFO[selectedMode].description}
                  </p>
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-4 mb-6">
                <div className="bg-green-50 p-4 rounded-lg">
                  <h3 className="font-semibold text-green-900 mb-2 flex items-center gap-2">
                    <svg
                      className="w-5 h-5"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                        clipRule="evenodd"
                      />
                    </svg>
                    Advantages
                  </h3>
                  <ul className="space-y-1">
                    {MODE_INFO[selectedMode].pros.map((pro, idx) => (
                      <li
                        key={idx}
                        className="text-sm text-gray-700 flex items-start gap-2"
                      >
                        <span className="text-green-600 mt-0.5">•</span>
                        <span>{pro}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="bg-yellow-50 p-4 rounded-lg">
                  <h3 className="font-semibold text-yellow-900 mb-2 flex items-center gap-2">
                    <svg
                      className="w-5 h-5"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                    Considerations
                  </h3>
                  <ul className="space-y-1">
                    {MODE_INFO[selectedMode].cons.map((con, idx) => (
                      <li
                        key={idx}
                        className="text-sm text-gray-700 flex items-start gap-2"
                      >
                        <span className="text-yellow-600 mt-0.5">•</span>
                        <span>{con}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
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
                    <p className="font-medium mb-1">Important:</p>
                    <p>
                      Switching modes will reload the application. Make sure
                      you've saved any unsaved work. Your existing data will
                      remain accessible in both modes.
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex gap-3 justify-end">
                <button
                  onClick={cancelModeChange}
                  className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmModeChange}
                  className="px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors font-medium"
                >
                  Switch to {MODE_INFO[selectedMode].title}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
