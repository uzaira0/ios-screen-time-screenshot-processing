import { useState, useCallback } from "react";
import { Modal } from "@/components/ui/Modal";

interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "warning" | "default";
}

/**
 * Hook that provides a styled confirm dialog (replaces window.confirm).
 *
 * Usage:
 *   const { confirm, ConfirmDialog } = useConfirmDialog();
 *   const ok = await confirm({ title: "Delete?", message: "This cannot be undone." });
 *   // Render <ConfirmDialog /> in your JSX
 */
export function useConfirmDialog() {
  const [state, setState] = useState<{
    options: ConfirmOptions;
    resolve: (value: boolean) => void;
  } | null>(null);

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      setState({ options, resolve });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    state?.resolve(true);
    setState(null);
  }, [state]);

  const handleCancel = useCallback(() => {
    state?.resolve(false);
    setState(null);
  }, [state]);

  const variantStyles = {
    danger: "bg-red-600 hover:bg-red-700",
    warning: "bg-amber-600 hover:bg-amber-700",
    default: "bg-primary-600 hover:bg-primary-700",
  };

  const ConfirmDialog = state ? (
    <Modal
      open
      onOpenChange={(open) => { if (!open) handleCancel(); }}
      title={state.options.title}
      size="sm"
    >
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
        {state.options.message}
      </p>
      <div className="flex justify-end gap-3">
        <button
          onClick={handleCancel}
          className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600"
        >
          {state.options.cancelLabel || "Cancel"}
        </button>
        <button
          onClick={handleConfirm}
          className={`px-4 py-2 text-sm font-medium text-white rounded-md ${variantStyles[state.options.variant || "default"]}`}
        >
          {state.options.confirmLabel || "Confirm"}
        </button>
      </div>
    </Modal>
  ) : null;

  return { confirm, ConfirmDialog };
}
