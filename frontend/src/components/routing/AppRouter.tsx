/**
 * Application Router
 *
 * Multi-user collaborative routes with authentication.
 * Feature availability is determined by the DI container's AppFeatures,
 * not by direct mode checks.
 */

import React from "react";
import { Routes, Route, Navigate } from "react-router";

// Pages
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";
import { AnnotationPage } from "@/pages/AnnotationPage";
import { ConsensusPage } from "@/pages/ConsensusPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ExportPage } from "@/pages/ExportPage";
import { UploadPage } from "@/pages/UploadPage";
import { HelpPage } from "@/pages/HelpPage";

// Lazy-load heavy pages. We attach a `.preload()` hook to each one and
// fire them all from a requestIdleCallback after the initial paint, so
// by the time the user actually clicks a Link the chunk is already
// in cache. This is what kills the "click → blank → spinner → page"
// stutter that read as 'navigation lag'.
function lazyWithPreload<T extends { default: React.ComponentType<unknown> }>(
  loader: () => Promise<T>,
): React.LazyExoticComponent<T["default"]> & { preload: () => Promise<T> } {
  const Lazy = React.lazy(loader) as React.LazyExoticComponent<T["default"]> & {
    preload: () => Promise<T>;
  };
  Lazy.preload = loader;
  return Lazy;
}

const AdminPage = lazyWithPreload(() =>
  import("@/pages/AdminPage").then((m) => ({ default: m.AdminPage })),
);
const ConsensusComparisonPage = lazyWithPreload(() =>
  import("@/pages/ConsensusComparisonPage").then((m) => ({
    default: m.ConsensusComparisonPage,
  })),
);
const PreprocessingPage = lazyWithPreload(() =>
  import("@/pages/PreprocessingPage").then((m) => ({
    default: m.PreprocessingPage,
  })),
);

// Auth guard
import { useAuthStore } from "@/store/authStore";
import { useFeatures } from "@/core/hooks/useServices";
import { useAuth } from "@/hooks/useAuth";
import { PreprocessingProvider } from "@/hooks/usePreprocessingWithDI";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { config } from "@/config";

/** Per-route ErrorBoundary so a crash on one page doesn't blank the entire
 *  app. The App-level boundary still catches anything that escapes a route. */
const RouteBoundary: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ErrorBoundary>{children}</ErrorBoundary>
);

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

// Redirect authenticated users away from login page. In local mode there
// is no login at all — the auto-auth bootstrap in App.tsx logs the user in
// on mount, so this route should never render LoginPage either way.
const LoginRoute: React.FC = () => {
  const { isAuthenticated } = useAuthStore();

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  if (config.isLocalMode) {
    return <Navigate to="/" replace />;
  }

  return <LoginPage />;
};

const ServerOnlyFallback = (
  <div className="flex items-center justify-center h-96">
    <span className="inline-block w-6 h-6 border-2 border-slate-300 border-t-primary-600 rounded-full animate-spin" />
  </div>
);

const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isAdmin } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};

export const AppRouter: React.FC = () => {
  const features = useFeatures();

  // Preload route chunks once the browser is idle so the first
  // navigation doesn't pay the chunk-fetch latency. Each .preload() is
  // idempotent — it just returns the same import promise.
  React.useEffect(() => {
    const w = window as unknown as { requestIdleCallback?: (cb: () => void) => number };
    const run = () => {
      void PreprocessingPage.preload();
      if (features.consensusComparison) void ConsensusComparisonPage.preload();
      if (features.admin) void AdminPage.preload();
    };
    if (typeof w.requestIdleCallback === "function") {
      w.requestIdleCallback(run);
    } else {
      setTimeout(run, 1500);
    }
  }, [features.admin, features.consensusComparison]);

  return (
    <Routes>
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <RouteBoundary>
              <HomePage />
            </RouteBoundary>
          </ProtectedRoute>
        }
      />
      <Route path="/login" element={<LoginRoute />} />
      <Route
        path="/annotate"
        element={
          <ProtectedRoute>
            <RouteBoundary>
              <AnnotationPage />
            </RouteBoundary>
          </ProtectedRoute>
        }
      />
      <Route
        path="/annotate/:id"
        element={
          <ProtectedRoute>
            <RouteBoundary>
              <AnnotationPage />
            </RouteBoundary>
          </ProtectedRoute>
        }
      />
      {/* Consensus — server only (requires multiple users) */}
      <Route
        path="/consensus"
        element={
          <ProtectedRoute>
            {features.consensusComparison ? (
              <RouteBoundary>
                <ConsensusPage />
              </RouteBoundary>
            ) : (
              <Navigate to="/" replace />
            )}
          </ProtectedRoute>
        }
      />
      {/* Cross-rater comparison — server only (requires multiple real users) */}
      <Route
        path="/consensus/compare/:screenshotId"
        element={
          <ProtectedRoute>
            {features.consensusComparison ? (
              <RouteBoundary>
                <React.Suspense fallback={ServerOnlyFallback}>
                  <ConsensusComparisonPage />
                </React.Suspense>
              </RouteBoundary>
            ) : (
              <Navigate to="/consensus" replace />
            )}
          </ProtectedRoute>
        }
      />
      {/* Upload (server only — WASM mode uploads via HomePage drag-and-drop) */}
      <Route
        path="/upload"
        element={
          <ProtectedRoute>
            {features.preprocessing ? (
              <RouteBoundary>
                <PreprocessingProvider>
                  <UploadPage />
                </PreprocessingProvider>
              </RouteBoundary>
            ) : (
              <Navigate to="/" replace />
            )}
          </ProtectedRoute>
        }
      />
      {/* Preprocessing Pipeline */}
      <Route
        path="/preprocessing"
        element={
          <ProtectedRoute>
            {features.preprocessing ? (
              <RouteBoundary>
                <React.Suspense fallback={ServerOnlyFallback}>
                  <PreprocessingProvider>
                    <PreprocessingPage />
                  </PreprocessingProvider>
                </React.Suspense>
              </RouteBoundary>
            ) : (
              <Navigate to="/" replace />
            )}
          </ProtectedRoute>
        }
      />
      {/* Legacy routes */}
      <Route path="/history" element={<Navigate to="/" replace />} />
      <Route path="/disputed" element={<Navigate to="/consensus" replace />} />
      {/* Admin (server only, admin role required) */}
      <Route
        path="/admin"
        element={
          <AdminRoute>
            {features.admin ? (
              <RouteBoundary>
                <React.Suspense fallback={ServerOnlyFallback}>
                  <AdminPage />
                </React.Suspense>
              </RouteBoundary>
            ) : (
              <Navigate to="/" replace />
            )}
          </AdminRoute>
        }
      />
      <Route
        path="/export"
        element={
          <ProtectedRoute>
            <RouteBoundary>
              <ExportPage />
            </RouteBoundary>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <RouteBoundary>
              <SettingsPage />
            </RouteBoundary>
          </ProtectedRoute>
        }
      />
      <Route
        path="/help"
        element={
          <RouteBoundary>
            <HelpPage />
          </RouteBoundary>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};
