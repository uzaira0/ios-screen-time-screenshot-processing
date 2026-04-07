import { useState, useCallback, type ReactNode } from "react";

interface CollapsibleSectionProps {
  title: string;
  storageKey: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

function getInitialState(storageKey: string, defaultOpen: boolean): boolean {
  try {
    const stored = localStorage.getItem(`collapsible:${storageKey}`);
    if (stored !== null) return stored === "1";
  } catch { /* localStorage unavailable */ }
  return defaultOpen;
}

export const CollapsibleSection = ({
  title,
  storageKey,
  defaultOpen = true,
  children,
}: CollapsibleSectionProps) => {
  const [isOpen, setIsOpen] = useState(() => getInitialState(storageKey, defaultOpen));

  const toggle = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev;
      try { localStorage.setItem(`collapsible:${storageKey}`, next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  }, [storageKey]);

  return (
    <div className="border-b border-slate-100 dark:border-slate-700 pb-2">
      <button
        onClick={toggle}
        className="flex items-center justify-between w-full text-xs text-slate-500 dark:text-slate-400 mb-1 hover:text-slate-700 dark:hover:text-slate-300 transition-colors"
        type="button"
      >
        <span>{title}</span>
        <svg
          className={`w-3 h-3 transition-transform ${isOpen ? "" : "-rotate-90"}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {isOpen && children}
    </div>
  );
};
