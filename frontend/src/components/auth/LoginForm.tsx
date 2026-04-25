import { useState, useEffect, FormEvent } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/services/apiClient";
import { config } from "@/config";
import { useSyncStore } from "@/core/implementations/wasm/sync";
import toast from "react-hot-toast";

export const LoginForm = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isCheckingPassword, setIsCheckingPassword] = useState(!config.isLocalMode);

  // Sync toggle state (local mode only)
  const [connectToServer, setConnectToServer] = useState(false);
  const [serverUrl, setServerUrl] = useState("");
  const [sitePassword, setSitePassword] = useState("");

  const { login } = useAuth();
  const navigate = useNavigate();

  // Check if password is required on mount (server mode only)
  useEffect(() => {
    if (config.isLocalMode) return;
    api.auth
      .isPasswordRequired()
      .then((required) => {
        setPasswordRequired(required);
      })
      .catch((err) => {
        console.warn("Failed to check password requirement:", err);
        setPasswordRequired(false);
      })
      .finally(() => {
        setIsCheckingPassword(false);
      });
  }, []);

  // Load persisted sync config on mount (local mode only)
  useEffect(() => {
    if (!config.isLocalMode) return;
    useSyncStore.getState().initConfig().then(() => {
      const { serverUrl: savedUrl, sitePassword: savedPw } = useSyncStore.getState();
      if (savedUrl) {
        setServerUrl(savedUrl);
        setSitePassword(savedPw);
      }
    });
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (config.isLocalMode) {
      const name = username.trim() || "User";
      login(1, name, undefined, "admin");

      // Handle sync configuration via store (single write path)
      if (connectToServer && serverUrl.trim()) {
        const store = useSyncStore.getState();
        store.setServerUrl(serverUrl.trim());
        store.setUsername(name);
        if (sitePassword) store.setSitePassword(sitePassword);
        await store.configureNow();

        // Fire-and-forget health check
        store.checkHealth().then((result) => {
          if (result.ok) {
            toast.success("Connected to server");
          } else {
            toast.error(`Server: ${result.error || "unreachable"}`);
          }
        });
      }

      toast.success(`Welcome, ${name}!`);
      navigate("/");
      return;
    }

    if (!username.trim()) return;

    if (passwordRequired && !password) {
      toast.error("Password is required");
      return;
    }

    setIsLoading(true);
    try {
      const user = await api.auth.login(
        username.trim(),
        passwordRequired ? password : undefined,
      );
      login(
        user.id,
        user.username,
        passwordRequired ? password : undefined,
        user.role,
      );
      toast.success(`Welcome, ${user.username}!`);
      navigate("/");
    } catch (error) {
      console.error("Login failed:", error);
      toast.error(error instanceof Error ? error.message : "Login failed");
    } finally {
      setIsLoading(false);
    }
  };

  const isFormValid = config.isLocalMode
    ? connectToServer ? !!serverUrl.trim() : true
    : username.trim() && (!passwordRequired || password);

  const subtitle = config.isLocalMode
    ? `${config.isTauri ? "Desktop Mode" : "Local Mode"} — Enter a username to get started`
    : passwordRequired
      ? "Enter your credentials to continue"
      : "Enter your username to continue";

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-slate-900 dark:text-slate-100">
            iOS Screen Time
          </h2>
          <p className="mt-1 text-center text-sm text-slate-500 dark:text-slate-400">
            Extract and verify hourly app usage data from iOS Screen Time screenshots.
          </p>
          <p className="mt-2 text-center text-sm text-slate-600 dark:text-slate-400">
            {subtitle}
          </p>
        </div>

        {isCheckingPassword ? (
          <div className="flex justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
          </div>
        ) : (
          <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
            <div className="rounded-md shadow-sm space-y-4">
              <div>
                <label htmlFor="username" className="sr-only">
                  Username
                </label>
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required={!config.isLocalMode}
                  minLength={3}
                  maxLength={50}
                  title="3-50 characters: letters, numbers, hyphens, underscores"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="appearance-none rounded-md relative block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 placeholder-slate-500 text-slate-900 dark:text-slate-100 dark:bg-slate-800 focus:outline-none focus:ring-primary-500 focus:border-primary-500 focus:z-10 sm:text-sm"
                  placeholder={config.isLocalMode ? "Username (optional)" : "Username"}
                />
              </div>

              {passwordRequired && (
                <div>
                  <label htmlFor="password" className="sr-only">
                    Password
                  </label>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="appearance-none rounded-md relative block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 placeholder-slate-500 text-slate-900 dark:text-slate-100 dark:bg-slate-800 focus:outline-none focus:ring-primary-500 focus:border-primary-500 focus:z-10 sm:text-sm"
                    placeholder="Access Password"
                  />
                </div>
              )}

              {/* Server sync toggle (local/desktop mode only) */}
              {config.isLocalMode && (
                <div className="border border-slate-200 dark:border-slate-700 rounded-md p-4 space-y-3">
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={connectToServer}
                      onChange={(e) => setConnectToServer(e.target.checked)}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-slate-300 dark:border-slate-600 rounded"
                    />
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                      Connect to Server (optional)
                    </span>
                  </label>
                  <p className="text-xs text-slate-500 dark:text-slate-400 ml-7">
                    Sync local data to a server for multi-user consensus
                  </p>

                  {connectToServer && (
                    <div className="ml-7 space-y-3">
                      <div>
                        <label
                          htmlFor="server-url"
                          className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1"
                        >
                          Server API URL
                        </label>
                        <input
                          id="server-url"
                          type="url"
                          required
                          value={serverUrl}
                          onChange={(e) => setServerUrl(e.target.value)}
                          className="appearance-none rounded-md relative block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 placeholder-slate-500 text-slate-900 dark:text-slate-100 dark:bg-slate-800 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                          placeholder="http://localhost:8002/api/v1"
                        />
                      </div>
                      <div>
                        <label
                          htmlFor="site-password"
                          className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1"
                        >
                          Site Password (optional)
                        </label>
                        <input
                          id="site-password"
                          type="password"
                          value={sitePassword}
                          onChange={(e) => setSitePassword(e.target.value)}
                          className="appearance-none rounded-md relative block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 placeholder-slate-500 text-slate-900 dark:text-slate-100 dark:bg-slate-800 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                          placeholder="Leave blank if not required"
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div>
              <button
                type="submit"
                disabled={!isFormValid || isLoading}
                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? "Logging in..." : config.isLocalMode ? "Get Started" : "Continue"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
