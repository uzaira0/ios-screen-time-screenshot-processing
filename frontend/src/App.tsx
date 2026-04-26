import { useEffect } from "react";
import { BrowserRouter, HashRouter } from "react-router";
import { Toaster } from "react-hot-toast";
import toast from "react-hot-toast";
import { AppRouter } from "./components/routing/AppRouter";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useWebSocket } from "./hooks/useWebSocket";
import { useAuthStore } from "./store/authStore";
import { config } from "./config";
import type {
  AnnotationSubmittedEvent,
  ScreenshotCompletedEvent,
  UserJoinedEvent,
  UserLeftEvent,
} from "./types/websocket";

/**
 * WebSocket integration component for real-time updates
 */
function WebSocketIntegration() {
  const { subscribe } = useWebSocket();
  const { isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated) return;

    const unsubscribeAnnotationSubmitted = subscribe(
      "annotation_submitted",
      (raw: unknown) => {
        const data = raw as AnnotationSubmittedEvent;
        toast.success(
          `${data.username} submitted annotation (${data.annotation_count}/${data.required_count})`,
          { duration: 4000 },
        );
      },
    );

    const unsubscribeScreenshotCompleted = subscribe(
      "screenshot_completed",
      (raw: unknown) => {
        const data = raw as ScreenshotCompletedEvent;
        toast.success(`Screenshot "${data.filename}" completed!`, {
          duration: 4000,
        });
      },
    );

    const unsubscribeUserJoined = subscribe(
      "user_joined",
      (raw: unknown) => {
        const data = raw as UserJoinedEvent;
        toast(`${data.username} joined (${data.active_users} online)`, {
          duration: 3000,
        });
      },
    );

    const unsubscribeUserLeft = subscribe(
      "user_left",
      (raw: unknown) => {
        const data = raw as UserLeftEvent;
        toast(`${data.username} left (${data.active_users} online)`, {
          duration: 3000,
        });
      },
    );

    return () => {
      unsubscribeAnnotationSubmitted();
      unsubscribeScreenshotCompleted();
      unsubscribeUserJoined();
      unsubscribeUserLeft();
    };
  }, [subscribe, isAuthenticated]);

  return null;
}

/**
 * Auto-bootstrap auth in local mode. There is no real account here — the
 * user owns the device, the data lives in OPFS/IndexedDB, and the username
 * is only used as a label on exported CSV rows. Asking for it on first
 * launch is meaningless friction; we collect it at export time instead.
 */
function LocalModeAutoAuth() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const login = useAuthStore((s) => s.login);

  useEffect(() => {
    if (!config.isLocalMode) return;
    if (isAuthenticated) return;
    login(1, "local", undefined, "admin");
  }, [isAuthenticated, login]);

  return null;
}

/**
 * Main App Component
 */
function App() {
  const Router = config.isTauri ? HashRouter : BrowserRouter;
  const routerProps = config.isTauri ? {} : { basename: config.basePath };

  return (
    <ErrorBoundary>
      <Router {...routerProps}>
        {config.isLocalMode && <LocalModeAutoAuth />}
        {config.hasApi && <WebSocketIntegration />}

        <Toaster
          position="top-right"
          toastOptions={{
            duration: 3000,
            style: {
              background: "#363636",
              color: "#fff",
            },
            success: {
              duration: 3000,
              iconTheme: {
                primary: "#10B981",
                secondary: "#fff",
              },
            },
            error: {
              duration: 4000,
              iconTheme: {
                primary: "#EF4444",
                secondary: "#fff",
              },
            },
          }}
        />

        <AppRouter />
      </Router>
    </ErrorBoundary>
  );
}

export default App;
