import toast from "react-hot-toast";

interface RetryToastOptions {
  message: string;
  onRetry: () => void | Promise<unknown>;
  retryLabel?: string;
  duration?: number;
}

/**
 * Show an error toast with a retry button.
 * Useful for operations that can fail due to network issues.
 */
export const toastErrorWithRetry = ({
  message,
  onRetry,
  retryLabel = "Retry",
  duration = 10000,
}: RetryToastOptions) => {
  toast.custom(
    (t) => (
      <div
        className={`${
          t.visible ? "animate-enter" : "animate-leave"
        } max-w-md w-full bg-white dark:bg-slate-800 shadow-lg rounded-lg pointer-events-auto flex ring-1 ring-black/5 dark:ring-slate-700`}
      >
        <div className="flex-1 w-0 p-4">
          <div className="flex items-start">
            <div className="flex-shrink-0 pt-0.5">
              <svg
                className="h-5 w-5 text-red-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <div className="ml-3 flex-1">
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Error</p>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{message}</p>
            </div>
          </div>
        </div>
        <div className="flex border-l border-slate-200 dark:border-slate-700">
          <button
            onClick={() => {
              toast.dismiss(t.id);
              onRetry();
            }}
            className="w-full border border-transparent rounded-none rounded-r-lg p-4 flex items-center justify-center text-sm font-medium text-primary-600 hover:text-primary-500 hover:bg-primary-50 focus:outline-none focus:ring-2 focus:ring-primary-500 transition-colors"
          >
            {retryLabel}
          </button>
        </div>
      </div>
    ),
    { duration },
  );
};

/**
 * Wrapper to execute an async operation with automatic retry toast on failure.
 */
export const withRetryToast = async <T,>(
  operation: () => Promise<T>,
  options: {
    errorMessage?: string;
    retryLabel?: string;
    onSuccess?: (result: T) => void;
    onFinalError?: (error: unknown) => void;
  } = {},
): Promise<T | undefined> => {
  const {
    errorMessage = "Operation failed",
    retryLabel = "Retry",
    onSuccess,
    onFinalError,
  } = options;

  try {
    const result = await operation();
    onSuccess?.(result);
    return result;
  } catch (error) {
    const message = error instanceof Error ? error.message : errorMessage;

    toastErrorWithRetry({
      message,
      onRetry: () => withRetryToast(operation, options),
      retryLabel,
    });

    onFinalError?.(error);
    return undefined;
  }
};
