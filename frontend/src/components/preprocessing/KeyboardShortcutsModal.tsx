import { useCallback, useMemo, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";

const SECTIONS = [
  {
    title: "Queue Navigation",
    shortcuts: [
      { keys: ["←", "→"], description: "Previous / next screenshot" },
      { keys: ["Esc"], description: "Exit queue, back to table" },
    ],
  },
  {
    title: "PHI Region Editor",
    shortcuts: [
      { keys: ["Shift", "D"], description: "Delete all auto-detected regions" },
      { keys: ["Ctrl", "Enter"], description: "Save regions & next" },
      { keys: ["Scroll"], description: "Zoom in / out on canvas" },
    ],
  },
  {
    title: "Annotation Workspace",
    shortcuts: [
      { keys: ["W", "A", "S", "D"], description: "Move grid up / left / down / right" },
      { keys: ["Shift", "W/A/S/D"], description: "Resize grid" },
      { keys: ["←", "→"], description: "Previous / next screenshot" },
      { keys: ["Ctrl", "Enter"], description: "Submit annotation" },
    ],
  },
  {
    title: "General",
    shortcuts: [
      { keys: ["?"], description: "Toggle this shortcut reference" },
    ],
  },
];

export const KeyboardShortcutsModal = ({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) => {
  return (
    <Modal open={isOpen} onOpenChange={(open) => !open && onClose()} title="Keyboard Shortcuts" size="sm">
      <div className="space-y-5 mt-3">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
              {section.title}
            </h4>
            <div className="space-y-1.5">
              {section.shortcuts.map((s, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-slate-600 dark:text-slate-300">
                    {s.description}
                  </span>
                  <div className="flex items-center gap-1">
                    {s.keys.map((key, ki) => (
                      <span key={ki}>
                        {ki > 0 && (
                          <span className="text-slate-400 mx-0.5">+</span>
                        )}
                        <kbd className="px-1.5 py-0.5 text-xs font-mono bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded text-slate-700 dark:text-slate-300">
                          {key}
                        </kbd>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
};

/** Hook that listens for "?" keypress and toggles the modal. */
export function useKeyboardShortcutsModal() {
  const [isOpen, setIsOpen] = useState(false);
  const toggle = useCallback(() => setIsOpen((v) => !v), []);

  const shortcuts = useMemo(() => [
    { key: "?", shiftKey: true, handler: toggle },
  ], [toggle]);
  useKeyboardShortcuts(shortcuts);

  return { isOpen, onClose: () => setIsOpen(false), toggle };
}
