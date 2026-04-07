import React, {
  createContext,
  useRef,
  useEffect,
  type ReactNode,
  useState,
} from "react";
import { ServiceContainer, bootstrapServices } from "../di";
import { createConfig, AppConfig } from "../config";
import { config as runtimeConfig } from "@/config";

export const ServiceContext = createContext<ServiceContainer | null>(null);

// Module-level singleton to survive React StrictMode unmount/remount cycles
let globalContainer: ServiceContainer | null = null;
let globalConfig: AppConfig | null = null;
let bootstrapPromise: Promise<ServiceContainer> | null = null;

// Clean up worker threads when the tab/window is closed
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => {
    if (globalContainer) {
      globalContainer.destroy();
      globalContainer = null;
      globalConfig = null;
    }
  });
}

function getOrCreateContainer(config: AppConfig): Promise<ServiceContainer> {
  // If we have a container and the config matches, reuse it
  if (
    globalContainer &&
    globalConfig &&
    globalConfig.mode === config.mode &&
    globalConfig.apiBaseUrl === config.apiBaseUrl
  ) {
    if (runtimeConfig.isDev) {
      console.log("[ServiceProvider] Reusing existing global container");
    }
    return Promise.resolve(globalContainer);
  }

  // If bootstrap is already in progress for this config, reuse the promise
  if (bootstrapPromise) return bootstrapPromise;

  // Otherwise create a new one
  if (runtimeConfig.isDev) {
    console.log(
      "[ServiceProvider] Creating new global container, mode:",
      config.mode,
    );
  }
  bootstrapPromise = bootstrapServices(config)
    .then((container) => {
      globalContainer = container;
      globalConfig = config;
      bootstrapPromise = null;
      return container;
    })
    .catch((err) => {
      bootstrapPromise = null; // Allow retry on next mount
      throw err;
    });
  return bootstrapPromise;
}

interface ServiceProviderProps {
  children: ReactNode;
  config?: AppConfig;
}

export const ServiceProvider: React.FC<ServiceProviderProps> = ({
  children,
  config,
}) => {
  // Create config once
  const [effectiveConfig] = useState(() => config || createConfig());
  const [container, setContainer] = useState<ServiceContainer | null>(
    globalContainer,
  );
  const [error, setError] = useState<string | null>(null);

  // Track mount count for debugging
  const mountCountRef = useRef(0);

  useEffect(() => {
    mountCountRef.current++;
    if (runtimeConfig.isDev) {
      console.log("[ServiceProvider] Mounted, count:", mountCountRef.current);
    }

    // Bootstrap services (async for WASM/Tauri code-splitting)
    if (!container) {
      getOrCreateContainer(effectiveConfig)
        .then(setContainer)
        .catch((err) => {
          console.error("[ServiceProvider] Bootstrap failed:", err);
          setError(
            err instanceof Error
              ? err.message
              : "Failed to initialize application services",
          );
        });
    }

    return () => {
      if (runtimeConfig.isDev) {
        console.log(
          "[ServiceProvider] Cleanup called, mount count:",
          mountCountRef.current,
          "— keeping services alive (module singleton)",
        );
      }
    };
  }, []);

  if (error) {
    return (
      <div role="alert" className="flex items-center justify-center min-h-screen p-8">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-xl font-semibold text-red-600">Application failed to start</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">{error}</p>
          <button
            type="button"
            className="px-4 py-2 text-sm bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }

  // Show nothing until services are ready (typically <1ms for server mode,
  // slightly longer for WASM due to dynamic import)
  if (!container) return null;

  return (
    <ServiceContext.Provider value={container}>
      {children}
    </ServiceContext.Provider>
  );
};
