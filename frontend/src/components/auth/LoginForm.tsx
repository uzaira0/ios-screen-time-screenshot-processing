import { useState, useEffect, FormEvent } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/services/apiClient";
import { config } from "@/config";
import toast from "react-hot-toast";

export const LoginForm = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isCheckingPassword, setIsCheckingPassword] = useState(!config.isLocalMode);

  const { login } = useAuth();
  const navigate = useNavigate();

  // Local mode auto-auths in App.tsx; this form is only mounted for the
  // server-backed deployment. Bail out defensively if anyone navigates
  // here in local mode.
  useEffect(() => {
    if (config.isLocalMode) {
      navigate("/", { replace: true });
      return;
    }
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
  }, [navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

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

  const isFormValid = !!username.trim() && (!passwordRequired || password);

  const subtitle = passwordRequired
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
                  required
                  minLength={3}
                  maxLength={50}
                  title="3-50 characters: letters, numbers, hyphens, underscores"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="appearance-none rounded-md relative block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 placeholder-slate-500 text-slate-900 dark:text-slate-100 dark:bg-slate-800 focus:outline-none focus:ring-primary-500 focus:border-primary-500 focus:z-10 sm:text-sm"
                  placeholder="Username"
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
            </div>

            <div>
              <button
                type="submit"
                disabled={!isFormValid || isLoading}
                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? "Logging in..." : "Continue"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
