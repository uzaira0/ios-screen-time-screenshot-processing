import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { clsx } from "clsx";

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  size?: "sm" | "md" | "lg" | "xl" | "full";
}

const sizeClasses = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
  full: "max-w-[90vw] max-h-[90vh]",
};

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  className,
  size = "md",
}: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content
          className={clsx(
            "fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50",
            "bg-white dark:bg-slate-800 rounded-lg shadow-xl p-6 w-full",
            "focus:outline-none",
            sizeClasses[size],
            className,
          )}
        >
          {title && (
            <Dialog.Title className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1">
              {title}
            </Dialog.Title>
          )}
          {description && (
            <Dialog.Description className="text-sm text-slate-500 dark:text-slate-400 mb-4">
              {description}
            </Dialog.Description>
          )}
          {children}
          <Dialog.Close asChild>
            <button
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 focus-ring rounded-sm"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
