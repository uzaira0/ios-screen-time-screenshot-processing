import { useState, useEffect, useRef, useCallback } from "react";
import type { Screenshot, ScreenshotListResponse } from "@/core/models";
import { FILTER_STATUS_LABELS, type FilterStatus } from "@/constants/processingStatus";

interface ScreenshotSelectorProps {
  currentScreenshot: Screenshot | null;
  screenshotList: ScreenshotListResponse | null;
  currentIndex: number;
  totalInFilter: number;
  hasNext: boolean;
  hasPrev: boolean;
  onNavigateNext: () => void;
  onNavigatePrev: () => void;
  onSelectScreenshot: (id: number) => void;
  onSearch: (search: string) => void;
  onLoadMore: () => void;
  isLoading: boolean;
  currentUsername: string | null;
}

export const ScreenshotSelector = ({
  currentScreenshot,
  screenshotList,
  currentIndex,
  totalInFilter,
  hasNext,
  hasPrev,
  onNavigateNext,
  onNavigatePrev,
  onSelectScreenshot,
  onSearch,
  onLoadMore,
  isLoading,
  currentUsername,
}: ScreenshotSelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [isOpen]);

  // Handle search with debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      onSearch(searchTerm);
    }, 300);

    return () => clearTimeout(timer);
  }, [searchTerm, onSearch]);

  // Load more screenshots when scrolling near the bottom of the list
  const scrollThrottled = useRef(false);
  const scrollTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => { clearTimeout(scrollTimer.current); }, []);

  const handleListScroll = useCallback(() => {
    const el = listRef.current;
    if (!el || !screenshotList?.has_next || scrollThrottled.current) return;

    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    if (nearBottom) {
      scrollThrottled.current = true;
      onLoadMore();
      // Throttle: ignore scroll events for 300ms after triggering a load
      scrollTimer.current = setTimeout(() => { scrollThrottled.current = false; }, 300);
    }
  }, [onLoadMore, screenshotList?.has_next]);

  const handleSelectScreenshot = (id: number) => {
    onSelectScreenshot(id);
    setIsOpen(false);
    setSearchTerm("");
  };

  const getVerificationBadge = (screenshot: Screenshot) => {
    const verifierUsernames = screenshot.verified_by_usernames || [];
    const verifierCount = verifierUsernames.length;
    const isVerifiedByMe =
      currentUsername !== null && verifierUsernames.includes(currentUsername);

    if (verifierCount === 0) {
      return null;
    }

    // Green if verified by current user, yellow if not
    const colorClasses = isVerifiedByMe
      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
      : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400";

    return (
      <span className={`ml-1 px-1.5 py-0.5 text-xs ${colorClasses} rounded font-medium`}>
        {verifierCount}
      </span>
    );
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "text-green-600";
      case "failed":
        return "text-red-600";
      case "pending":
        return "text-primary-600";
      case "skipped":
        return "text-slate-500";
      default:
        return "text-slate-600";
    }
  };

  return (
    <div className="flex items-center gap-2" ref={dropdownRef} data-testid="screenshot-selector">
      {/* Previous Button */}
      <button
        onClick={onNavigatePrev}
        disabled={!hasPrev || isLoading}
        className={`p-1.5 rounded transition-colors ${
          hasPrev && !isLoading
            ? "bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-700 dark:hover:bg-slate-600 dark:text-slate-300"
            : "bg-slate-50 text-slate-300 cursor-not-allowed dark:bg-slate-800 dark:text-slate-600"
        }`}
        aria-label="Previous screenshot"
        title="Previous screenshot (Shift+Left)"
        data-testid="navigate-prev"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 19l-7-7 7-7"
          />
        </svg>
      </button>

      {/* Screenshot Selector Dropdown */}
      <div className="relative flex-1 min-w-0">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="w-full px-2 py-1.5 text-left bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded hover:border-slate-400 dark:hover:border-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 flex items-center gap-2"
        >
          {currentScreenshot ? (
            <>
              <span className="font-semibold text-slate-900 dark:text-slate-100 whitespace-nowrap">
                #{currentScreenshot.id}
              </span>
              <span className="text-xs text-slate-500 truncate">
                {currentScreenshot.participant_id || ""}
                {currentScreenshot.screenshot_date && ` · ${currentScreenshot.screenshot_date}`}
              </span>
              {(() => {
                const verifierUsernames =
                  currentScreenshot.verified_by_usernames || [];
                const verifierCount = verifierUsernames.length;
                if (verifierCount === 0) return null;
                const isVerifiedByMe =
                  currentUsername !== null &&
                  verifierUsernames.includes(currentUsername);
                const colorClasses = isVerifiedByMe
                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                  : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400";
                return (
                  <span className={`px-1.5 py-0.5 text-[10px] ${colorClasses} rounded font-medium whitespace-nowrap`}>
                    {verifierCount}
                  </span>
                );
              })()}
              <span className="text-xs text-slate-400 whitespace-nowrap ml-auto" data-testid="navigation-info">
                {currentIndex}/{totalInFilter}
              </span>
            </>
          ) : (
            <span className="text-slate-400 flex-1">Select...</span>
          )}
          <svg
            className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </button>

        {/* Dropdown Menu */}
        {isOpen && (
          <div className="absolute z-50 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-600 rounded-lg shadow-lg max-h-80 overflow-hidden">
            {/* Search Input */}
            <div className="p-2 border-b border-slate-200 dark:border-slate-700">
              <input
                ref={searchInputRef}
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search by ID or participant..."
                className="w-full px-2 py-1 text-sm border border-slate-200 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-500"
              />
            </div>

            {/* Screenshot List */}
            <div className="max-h-52 overflow-y-auto" ref={listRef} onScroll={handleListScroll}>
              {screenshotList?.items.map((screenshot: Screenshot) => {
                // Extract filename from file_path
                const filename = screenshot.file_path?.split("/").pop() || "";
                const dateStr = screenshot.screenshot_date || "";
                return (
                  <button
                    key={screenshot.id}
                    onClick={() => handleSelectScreenshot(screenshot.id)}
                    className={`w-full px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-700 flex items-center justify-between ${
                      currentScreenshot?.id === screenshot.id
                        ? "bg-primary-50 dark:bg-primary-900/20"
                        : ""
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-medium whitespace-nowrap">#{screenshot.id}</span>
                      <span className="text-xs text-slate-600 dark:text-slate-400 truncate">
                        {screenshot.participant_id || ""}
                        {dateStr && ` · ${dateStr}`}
                        {filename && ` · ${filename}`}
                      </span>
                      {getVerificationBadge(screenshot)}
                    </div>
                    <span
                      className={`text-xs flex-shrink-0 ml-2 ${getStatusColor(screenshot.processing_status)}`}
                    >
                      {FILTER_STATUS_LABELS[screenshot.processing_status as FilterStatus] || screenshot.processing_status}
                    </span>
                  </button>
                );
              })}
              {screenshotList?.items.length === 0 && (
                <div className="px-3 py-4 text-center text-slate-500 text-sm">
                  No screenshots found
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Next Button */}
      <button
        onClick={onNavigateNext}
        disabled={!hasNext || isLoading}
        className={`p-1.5 rounded transition-colors ${
          hasNext && !isLoading
            ? "bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-700 dark:hover:bg-slate-600 dark:text-slate-300"
            : "bg-slate-50 text-slate-300 cursor-not-allowed dark:bg-slate-800 dark:text-slate-600"
        }`}
        aria-label="Next screenshot"
        title="Next screenshot (Shift+Right)"
        data-testid="navigate-next"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
      </button>
    </div>
  );
};
