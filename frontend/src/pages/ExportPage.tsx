import { useState } from "react";
import { Layout } from "@/components/layout/Layout";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useScreenshotService } from "@/core/hooks/useServices";
import { config } from "@/config";
import { Download } from "lucide-react";
import toast from "react-hot-toast";
import { useAuthStore } from "@/store/authStore";

export const ExportPage = () => {
  const screenshotService = useScreenshotService();
  const [isExporting, setIsExporting] = useState(false);
  const [scorerId, setScorerId] = useState(() => {
    try { return localStorage.getItem("scorerId") ?? ""; } catch { return ""; }
  });

  const runExport = async () => {
    setIsExporting(true);
    try {
      const trimmed = scorerId.trim();
      if (config.isLocalMode && trimmed) {
        try { localStorage.setItem("scorerId", trimmed); } catch { /* ignore */ }
        const auth = useAuthStore.getState();
        if (auth.username !== trimmed) {
          auth.login(auth.userId ?? 1, trimmed, undefined, auth.role ?? "admin");
        }
      }

      const csvData = await screenshotService.exportCSV();
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const blob = new Blob([csvData], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `annotations_export_${timestamp}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success("Exported as CSV");
    } catch (err) {
      if (config.isDev) console.error("Export failed:", err);
      toast.error("Export failed. Please try again.");
    } finally {
      setIsExporting(false);
    }
  };

  const canExport = !config.isLocalMode || scorerId.trim().length > 0;

  return (
    <Layout>
      <div className="max-w-xl mx-auto px-4 py-8 space-y-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Export</h1>

        <Card padding="lg">
          <div className="space-y-4">
            <div>
              <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">CSV Export</h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Downloads all annotated screenshots as a CSV file containing screenshot ID, group,
                participant, date, app title, total usage, and 24 hourly values (h0–h23) in minutes.
              </p>
            </div>

            {config.isLocalMode && (
              <div>
                <label
                  htmlFor="scorer-id"
                  className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1"
                >
                  Scorer ID
                </label>
                <input
                  id="scorer-id"
                  type="text"
                  value={scorerId}
                  onChange={(e) => setScorerId(e.target.value)}
                  placeholder="e.g. JD, rater-1, alice"
                  className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && canExport) {
                      e.preventDefault();
                      void runExport();
                    }
                  }}
                />
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  Written into every CSV row for cross-rater comparison.
                </p>
              </div>
            )}

            <Button
              variant="primary"
              onClick={runExport}
              loading={isExporting}
              disabled={!canExport}
              icon={<Download className="h-4 w-4" />}
            >
              {isExporting ? "Exporting…" : "Export CSV"}
            </Button>
          </div>
        </Card>
      </div>
    </Layout>
  );
};
