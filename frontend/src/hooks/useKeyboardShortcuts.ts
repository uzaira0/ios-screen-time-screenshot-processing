import { useEffect } from "react";

interface ShortcutConfig {
  key: string;
  handler: () => void;
  ctrlKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
}

export const useKeyboardShortcuts = (shortcuts: ShortcutConfig[]) => {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't trigger shortcuts when typing in input fields
      const target = event.target as HTMLElement;
      const isTyping =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      if (isTyping) {
        return;
      }

      for (const shortcut of shortcuts) {
        // Handle special keys like Escape, Enter which don't need toLowerCase
        const eventKey = event.key;
        const shortcutKey = shortcut.key;
        const keyMatches =
          eventKey === shortcutKey ||
          eventKey.toLowerCase() === shortcutKey.toLowerCase();
        const ctrlMatches = shortcut.ctrlKey ? event.ctrlKey : !event.ctrlKey;
        const altMatches = shortcut.altKey ? event.altKey : !event.altKey;
        const shiftMatches = shortcut.shiftKey
          ? event.shiftKey
          : !event.shiftKey;

        if (keyMatches && ctrlMatches && altMatches && shiftMatches) {
          event.preventDefault();
          shortcut.handler();
          break;
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcuts]);
};
