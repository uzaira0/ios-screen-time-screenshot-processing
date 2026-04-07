import { Component, ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  override render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex items-center justify-center h-96">
          <div className="text-center max-w-md p-6">
            <AlertTriangle className="h-16 w-16 text-amber-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">
              Something went wrong
            </h2>
            <p className="text-slate-600 dark:text-slate-400 mb-4">
              An unexpected error occurred while rendering this component.
            </p>
            {this.state.error && (
              <details className="text-left bg-slate-50 dark:bg-slate-800 p-4 rounded-md mb-4">
                <summary className="cursor-pointer text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  Error Details
                </summary>
                <pre className="text-xs text-red-600 overflow-auto">
                  {this.state.error.message}
                  {"\n"}
                  {this.state.error.stack}
                </pre>
              </details>
            )}
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-700 focus-ring"
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
