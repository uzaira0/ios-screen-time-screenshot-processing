import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router";
import { Layout } from "@/components/layout/Layout";
import { Modal } from "@/components/ui/Modal";
import {
  api,
  ScreenshotComparison,
  VerifierAnnotation,
} from "@/services/apiClient";
import toast from "react-hot-toast";
import { config } from "@/config";

const API_BASE_URL = config.apiBaseUrl;

export const ConsensusComparisonPage = () => {
  const { screenshotId } = useParams<{ screenshotId: string }>();
  const navigate = useNavigate();
  const [comparison, setComparison] = useState<ScreenshotComparison | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState(false);
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [resolutionValues, setResolutionValues] = useState<{
    hourly_values: Record<string, number>;
    extracted_title: string;
    extracted_total: string;
    resolution_notes: string;
  }>({
    hourly_values: {},
    extracted_title: "",
    extracted_total: "",
    resolution_notes: "",
  });

  const loadComparison = useCallback(async (id: number) => {
    try {
      setLoading(true);
      const data = await api.consensus.getScreenshotComparison(id);
      setComparison(data);

      // Initialize resolution values from first verifier
      const first = data.verifier_annotations[0];
      if (first) {
        setResolutionValues({
          hourly_values: { ...first.hourly_values },
          extracted_title: first.extracted_title || "",
          extracted_total: first.extracted_total || "",
          resolution_notes: "",
        });
      }
    } catch (error) {
      console.error("Failed to load comparison:", error);
      toast.error("Failed to load comparison data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (screenshotId) {
      loadComparison(parseInt(screenshotId, 10));
    }
  }, [screenshotId, loadComparison]);

  const handleResolve = async () => {
    if (!comparison) return;

    try {
      setResolving(true);
      await api.consensus.resolveDispute(comparison.screenshot_id, {
        hourly_values: resolutionValues.hourly_values,
        ...(resolutionValues.extracted_title && { extracted_title: resolutionValues.extracted_title }),
        ...(resolutionValues.extracted_total && { extracted_total: resolutionValues.extracted_total }),
        ...(resolutionValues.resolution_notes && { resolution_notes: resolutionValues.resolution_notes }),
      });
      toast.success("Dispute resolved successfully");
      setShowResolveModal(false);
      // Reload to show updated state
      loadComparison(comparison.screenshot_id);
    } catch (error) {
      console.error("Failed to resolve:", error);
      toast.error(
        error instanceof Error ? error.message : "Failed to resolve dispute",
      );
    } finally {
      setResolving(false);
    }
  };

  const handleSelectValue = (
    field: string,
    _userId: string,
    value: string | number | null,
  ) => {
    if (field.startsWith("hourly_")) {
      const hour = field.replace("hourly_", "");
      setResolutionValues((prev) => ({
        ...prev,
        hourly_values: {
          ...prev.hourly_values,
          [hour]: typeof value === "number" ? value : 0,
        },
      }));
    } else if (field === "title") {
      setResolutionValues((prev) => ({
        ...prev,
        extracted_title: String(value || ""),
      }));
    } else if (field === "total") {
      setResolutionValues((prev) => ({
        ...prev,
        extracted_total: String(value || ""),
      }));
    }
  };

  const handleBack = () => {
    if (comparison?.group_id) {
      navigate(
        `/consensus?group=${comparison.group_id}&tier=${comparison.tier}`,
      );
    } else {
      navigate("/consensus");
    }
  };

  // Get all hours that have data
  const getAllHours = (annotations: VerifierAnnotation[]): string[] => {
    const hours = new Set<string>();
    annotations.forEach((ann) => {
      Object.keys(ann.hourly_values).forEach((h) => hours.add(h));
    });
    return Array.from(hours).sort((a, b) => parseInt(a) - parseInt(b));
  };

  // Check if a field has differences
  const fieldHasDifference = (field: string): boolean => {
    return comparison?.differences.some((d) => d.field === field) || false;
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        </div>
      </Layout>
    );
  }

  if (!comparison) {
    return (
      <Layout>
        <div className="text-center py-12">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
            Screenshot not found
          </h2>
          <button
            onClick={() => navigate("/consensus")}
            className="mt-4 text-primary-600 hover:text-primary-700"
          >
            Back to Consensus
          </button>
        </div>
      </Layout>
    );
  }

  const hours = getAllHours(comparison.verifier_annotations);
  const tierColors = {
    single_verified: "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-400",
    agreed: "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-400",
    disputed: "bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-400",
  };

  return (
    <Layout>
      <div className="py-6 px-4 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <button
              onClick={handleBack}
              className="text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 flex items-center gap-1 mb-2"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 19l-7-7 7-7"
                />
              </svg>
              Back
            </button>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
              Screenshot #{comparison.screenshot_id}
            </h1>
            <div className="flex items-center gap-3 mt-2">
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${tierColors[comparison.tier]}`}
              >
                {comparison.tier
                  .replace("_", " ")
                  .replace(/\b\w/g, (l) => l.toUpperCase())}
              </span>
              {comparison.participant_id && (
                <span className="text-purple-600">
                  {comparison.participant_id}
                </span>
              )}
              {comparison.screenshot_date && (
                <span className="text-slate-500">
                  {new Date(comparison.screenshot_date).toLocaleDateString()}
                </span>
              )}
            </div>
          </div>

          {comparison.tier === "disputed" && !comparison.is_resolved && (
            <button
              onClick={() => setShowResolveModal(true)}
              className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors"
            >
              Resolve Dispute
            </button>
          )}
        </div>

        {/* Resolution Status Banner */}
        {comparison.is_resolved && (
          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <svg className="w-5 h-5 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h3 className="font-semibold text-green-800 dark:text-green-300">Dispute Resolved</h3>
            </div>
            <div className="text-sm text-green-700 dark:text-green-400 space-y-1">
              {comparison.resolved_by_username && (
                <p>Resolved by: <span className="font-medium">{comparison.resolved_by_username}</span></p>
              )}
              {comparison.resolved_at && (
                <p>Resolved at: {new Date(comparison.resolved_at).toLocaleString()}</p>
              )}
              {comparison.resolved_title && (
                <p>Resolved title: <span className="font-mono bg-green-100 dark:bg-green-900/30 px-1 rounded">{comparison.resolved_title}</span></p>
              )}
              {comparison.resolved_total && (
                <p>Resolved total: <span className="font-mono bg-green-100 dark:bg-green-900/30 px-1 rounded">{comparison.resolved_total}</span></p>
              )}
            </div>
          </div>
        )}

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Screenshot Image */}
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">
              Screenshot
            </h2>
            <img
              src={`${API_BASE_URL}/screenshots/${comparison.screenshot_id}/image`}
              alt={`Screenshot ${comparison.screenshot_id}`}
              className="w-full rounded-lg border border-slate-200"
            />
          </div>

          {/* Comparison Table */}
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
            <div className="p-4 border-b border-slate-200 dark:border-slate-700">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                Verifier Comparison
              </h2>
              <p className="text-sm text-slate-500 mt-1">
                {comparison.verifier_annotations.length} verifier
                {comparison.verifier_annotations.length !== 1 ? "s" : ""}
                {comparison.differences.length > 0 && (
                  <span className="text-red-600 ml-2">
                    ({comparison.differences.length} difference
                    {comparison.differences.length !== 1 ? "s" : ""})
                  </span>
                )}
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-700/50">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-slate-700 dark:text-slate-300">
                      Field
                    </th>
                    {comparison.verifier_annotations.map((ann) => (
                      <th
                        key={ann.user_id}
                        className="px-4 py-3 text-left font-medium text-slate-700 dark:text-slate-300"
                      >
                        {ann.username}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                  {/* Title Row */}
                  <tr
                    className={fieldHasDifference("title") ? "bg-red-50 dark:bg-red-900/20" : ""}
                  >
                    <td className="px-4 py-2 font-medium text-slate-900 dark:text-slate-200">
                      Title
                    </td>
                    {comparison.verifier_annotations.map((ann) => (
                      <td key={ann.user_id} className="px-4 py-2 text-slate-700 dark:text-slate-300">
                        {ann.extracted_title || "-"}
                      </td>
                    ))}
                  </tr>

                  {/* Total Row */}
                  <tr
                    className={fieldHasDifference("total") ? "bg-red-50 dark:bg-red-900/20" : ""}
                  >
                    <td className="px-4 py-2 font-medium text-slate-900 dark:text-slate-200">
                      Total
                    </td>
                    {comparison.verifier_annotations.map((ann) => (
                      <td key={ann.user_id} className="px-4 py-2 text-slate-700 dark:text-slate-300">
                        {ann.extracted_total || "-"}
                      </td>
                    ))}
                  </tr>

                  {/* Hourly Values */}
                  {hours.map((hour) => (
                    <tr
                      key={hour}
                      className={
                        fieldHasDifference(`hourly_${hour}`) ? "bg-red-50 dark:bg-red-900/20" : ""
                      }
                    >
                      <td className="px-4 py-2 font-medium text-slate-900 dark:text-slate-200">
                        Hour {hour}
                      </td>
                      {comparison.verifier_annotations.map((ann) => (
                        <td
                          key={ann.user_id}
                          className="px-4 py-2 text-slate-700 dark:text-slate-300"
                        >
                          {ann.hourly_values[hour] !== undefined
                            ? ann.hourly_values[hour]
                            : "-"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Differences Summary */}
        {comparison.differences.length > 0 && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <h3 className="font-semibold text-red-800 dark:text-red-300 mb-2">
              Differences Found
            </h3>
            <ul className="space-y-1">
              {comparison.differences.map((diff, i) => (
                <li key={i} className="text-sm text-red-700 dark:text-red-400">
                  <span className="font-medium">
                    {diff.field.replace("hourly_", "Hour ")}:
                  </span>{" "}
                  {Object.entries(diff.values).map(([userId, value], j) => (
                    <span key={userId}>
                      {j > 0 && " vs "}
                      <span className="font-mono">
                        {String(value ?? "null")}
                      </span>
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Resolve Modal */}
      <Modal
        open={showResolveModal}
        onOpenChange={setShowResolveModal}
        title="Resolve Dispute"
        description="Select or edit the correct values for each field"
        size="lg"
      >
        <div className="space-y-4 max-h-[60vh] overflow-y-auto">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Title
            </label>
            <div className="space-y-2">
              {comparison.verifier_annotations.map((ann) => (
                <label
                  key={ann.user_id}
                  className="flex items-center gap-2"
                >
                  <input
                    type="radio"
                    name="title"
                    checked={
                      resolutionValues.extracted_title ===
                      (ann.extracted_title || "")
                    }
                    onChange={() =>
                      setResolutionValues((prev) => ({
                        ...prev,
                        extracted_title: ann.extracted_title || "",
                      }))
                    }
                    className="text-primary-600"
                  />
                  <span className="text-sm text-slate-600 dark:text-slate-400">
                    {ann.username}:
                  </span>
                  <span className="text-sm">
                    {ann.extracted_title || "(empty)"}
                  </span>
                </label>
              ))}
              <input
                type="text"
                value={resolutionValues.extracted_title}
                onChange={(e) =>
                  setResolutionValues((prev) => ({
                    ...prev,
                    extracted_title: e.target.value,
                  }))
                }
                className="mt-2 w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-sm dark:bg-slate-700 dark:text-slate-200"
                placeholder="Or enter custom value..."
              />
            </div>
          </div>

          {/* Total */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Total
            </label>
            <div className="space-y-2">
              {comparison.verifier_annotations.map((ann) => (
                <label
                  key={ann.user_id}
                  className="flex items-center gap-2"
                >
                  <input
                    type="radio"
                    name="total"
                    checked={
                      resolutionValues.extracted_total ===
                      (ann.extracted_total || "")
                    }
                    onChange={() =>
                      setResolutionValues((prev) => ({
                        ...prev,
                        extracted_total: ann.extracted_total || "",
                      }))
                    }
                    className="text-primary-600"
                  />
                  <span className="text-sm text-slate-600 dark:text-slate-400">
                    {ann.username}:
                  </span>
                  <span className="text-sm">
                    {ann.extracted_total || "(empty)"}
                  </span>
                </label>
              ))}
              <input
                type="text"
                value={resolutionValues.extracted_total}
                onChange={(e) =>
                  setResolutionValues((prev) => ({
                    ...prev,
                    extracted_total: e.target.value,
                  }))
                }
                className="mt-2 w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-sm dark:bg-slate-700 dark:text-slate-200"
                placeholder="Or enter custom value..."
              />
            </div>
          </div>

          {/* Differing Hourly Values */}
          {comparison.differences
            .filter((d) => d.field.startsWith("hourly_"))
            .map((diff) => {
              const hour = diff.field.replace("hourly_", "");
              return (
                <div key={diff.field}>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Hour {hour}
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {comparison.verifier_annotations.map((ann) => {
                      const value = ann.hourly_values[hour] ?? null;
                      return (
                        <button
                          key={ann.user_id}
                          onClick={() =>
                            handleSelectValue(
                              diff.field,
                              String(ann.user_id),
                              value,
                            )
                          }
                          className={`px-3 py-1 rounded border text-sm ${
                            resolutionValues.hourly_values[hour] === value
                              ? "bg-primary-100 dark:bg-primary-900/30 border-primary-500 text-primary-700 dark:text-primary-400"
                              : "bg-white dark:bg-slate-700 border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-600"
                          }`}
                        >
                          {ann.username}: {value ?? "null"}
                        </button>
                      );
                    })}
                    <input
                      type="number"
                      value={resolutionValues.hourly_values[hour] ?? ""}
                      onChange={(e) =>
                        setResolutionValues((prev) => ({
                          ...prev,
                          hourly_values: {
                            ...prev.hourly_values,
                            [hour]: parseFloat(e.target.value) || 0,
                          },
                        }))
                      }
                      className="w-20 px-2 py-1 border border-slate-300 dark:border-slate-600 rounded text-sm dark:bg-slate-700 dark:text-slate-200"
                      placeholder="Custom"
                      min="0"
                      max="60"
                    />
                  </div>
                </div>
              );
            })}

          {/* Resolution Notes */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Resolution Notes (optional)
            </label>
            <textarea
              value={resolutionValues.resolution_notes}
              onChange={(e) =>
                setResolutionValues((prev) => ({
                  ...prev,
                  resolution_notes: e.target.value,
                }))
              }
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-md text-sm dark:bg-slate-700 dark:text-slate-200"
              rows={2}
              placeholder="Add any notes about how this dispute was resolved..."
            />
          </div>
        </div>

        <div className="pt-4 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-3 mt-4">
          <button
            onClick={() => setShowResolveModal(false)}
            disabled={resolving}
            className="px-4 py-2 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            onClick={handleResolve}
            disabled={resolving}
            className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg disabled:opacity-50 flex items-center gap-2"
          >
            {resolving ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Resolving...
              </>
            ) : (
              "Resolve Dispute"
            )}
          </button>
        </div>
      </Modal>
    </Layout>
  );
};
