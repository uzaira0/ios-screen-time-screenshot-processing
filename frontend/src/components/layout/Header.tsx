import { useState } from "react";
import { Link, useSearchParams, useLocation, useNavigate } from "react-router";
import { useAuth } from "@/hooks/useAuth";
import { FILTER_STATUS_LABELS, type FilterStatus } from "@/constants/processingStatus";
import { Menu, X, LogOut, HelpCircle } from "lucide-react";
import { useThemeStore, THEME_OPTIONS, THEME_CYCLE } from "@/store/themeStore";
import { useFeatures } from "@/core/hooks/useServices";
import { config } from "@/config";
import { useWebSocket } from "@/hooks/useWebSocket";

export const Header = () => {
  const { username, isAuthenticated, isAdmin, logout } = useAuth();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { mode: themeMode, setMode: setThemeMode } = useThemeStore();
  const features = useFeatures();

  // Reactive connection state — no polling needed
  const { connected } = useWebSocket();

  const ThemeIcon = (THEME_OPTIONS.find((o) => o.value === themeMode) ?? THEME_OPTIONS[0]!).icon;

  // Get current filter context from URL
  const groupId = searchParams.get("group");
  const participantId = searchParams.get("participant_id");
  const processingStatus = searchParams.get("processing_status");
  const isAnnotatePage = location.pathname === "/annotate";

  const navLinks = [
    // Server mode: separate upload page. WASM mode: loading is on Home page.
    ...(!config.isLocalMode && features.preprocessing ? [{ to: "/upload", label: "Upload" }] : []),
    ...(features.preprocessing ? [{ to: "/preprocessing", label: "Preprocessing" }] : []),
    { to: "/", label: "Groups" },
    { to: "/annotate", label: "Annotate" },
    ...(!config.isLocalMode ? [{ to: "/consensus", label: "Consensus" }] : []),
    { to: "/settings", label: "Settings" },
    ...(features.admin && isAdmin ? [{ to: "/admin", label: "Admin" }] : []),
  ];

  return (
    <header className="bg-white dark:bg-slate-800 shadow-sm border-b border-slate-200 dark:border-slate-700">
      <div className="px-4">
        <div className="flex justify-between items-center h-16">
          {/* Left: Logo and Nav */}
          <div className="flex items-center space-x-8">
            <Link to="/" className="text-xl font-bold text-primary-700 font-heading focus-ring rounded">
              iOS Screen Time
            </Link>

            {/* Desktop Navigation */}
            {isAuthenticated && (
              <nav className="hidden md:flex space-x-1">
                {navLinks.map((link) => (
                  <Link
                    key={link.to}
                    to={link.to}
                    className="text-slate-600 dark:text-slate-300 hover:text-primary-700 dark:hover:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/30 px-3 py-2 rounded-md text-sm font-medium transition-colors focus-ring"
                  >
                    {link.label}
                  </Link>
                ))}
              </nav>
            )}
          </div>

          {/* Center: Queue Context Indicator */}
          {isAnnotatePage && (groupId || participantId || processingStatus) && (
            <div className="absolute left-1/2 transform -translate-x-1/2 hidden lg:flex items-center gap-2 px-3 py-1 bg-slate-100 dark:bg-slate-700 rounded-md text-sm">
              <span className="text-slate-500 dark:text-slate-400">Queue:</span>
              {groupId && (
                <span className="font-medium text-slate-700 dark:text-slate-200">{groupId}</span>
              )}
              {groupId && (participantId || processingStatus) && (
                <span className="text-slate-400 dark:text-slate-500">/</span>
              )}
              {participantId && (
                <span className="font-medium text-purple-600">
                  {participantId}
                </span>
              )}
              {participantId && processingStatus && (
                <span className="text-slate-400">/</span>
              )}
              {processingStatus && (
                <>
                  <span className="text-slate-500">Status:</span>
                  <span
                    className={"font-medium " + (
                      processingStatus === "completed"
                        ? "text-green-600"
                        : processingStatus === "failed"
                          ? "text-red-600"
                          : processingStatus === "pending"
                            ? "text-primary-600"
                            : "text-slate-600"
                    )}
                  >
                    {FILTER_STATUS_LABELS[processingStatus as FilterStatus] || processingStatus}
                  </span>
                </>
              )}
            </div>
          )}

          {/* Right: User info + Mobile menu toggle */}
          <div className="flex items-center space-x-4">
            {isAuthenticated && username ? (
              <>
                {/* Online/offline indicator (server mode only) */}
                {!config.isLocalMode && (
                  <span
                    className="hidden sm:inline-flex items-center gap-1.5 text-xs"
                    title={connected ? "WebSocket connected" : "WebSocket disconnected"}
                  >
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${
                        connected
                          ? "bg-green-500"
                          : "bg-red-500"
                      }`}
                    />
                    <span className={connected ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
                      {connected ? "Connected" : "Offline"}
                    </span>
                  </span>
                )}
                <span className="text-sm text-slate-700 dark:text-slate-300 hidden sm:inline">
                  Welcome, <span className="font-medium">{username}</span>
                </span>
                <Link
                  to="/help"
                  className="p-2 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-md transition-colors focus-ring"
                  aria-label="Help"
                  title="Help"
                >
                  <HelpCircle className="h-4 w-4" />
                </Link>
                {!config.isLocalMode && (
                  <button
                    onClick={() => setThemeMode(THEME_CYCLE[themeMode])}
                    className="p-2 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-md transition-colors focus-ring"
                    aria-label={`Theme: ${themeMode}. Click to switch.`}
                    title={`Theme: ${themeMode}`}
                  >
                    <ThemeIcon className="h-4 w-4" />
                  </button>
                )}
                <button
                  onClick={() => { logout(); navigate("/login"); }}
                  className="hidden md:inline-flex items-center gap-2 bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-200 px-4 py-2 rounded-md text-sm font-medium transition-colors focus-ring"
                  aria-label="Logout"
                >
                  <LogOut className="h-4 w-4" />
                  Logout
                </button>
                {/* Mobile hamburger */}
                <button
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="md:hidden p-2 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-md focus-ring"
                  aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
                  aria-expanded={mobileMenuOpen}
                >
                  {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
                </button>
              </>
            ) : (
              <Link
                to="/login"
                className="bg-primary-600 hover:bg-primary-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors focus-ring"
              >
                Login
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Mobile Navigation */}
      {mobileMenuOpen && isAuthenticated && (
        <nav className="md:hidden border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-2 space-y-1">
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              onClick={() => setMobileMenuOpen(false)}
              className="block text-slate-600 dark:text-slate-300 hover:text-primary-700 dark:hover:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/30 px-3 py-2 rounded-md text-sm font-medium transition-colors focus-ring"
            >
              {link.label}
            </Link>
          ))}
          <button
            onClick={() => { logout(); setMobileMenuOpen(false); navigate("/login"); }}
            className="w-full text-left text-slate-600 dark:text-slate-300 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 px-3 py-2 rounded-md text-sm font-medium transition-colors focus-ring flex items-center gap-2"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </nav>
      )}
    </header>
  );
};
