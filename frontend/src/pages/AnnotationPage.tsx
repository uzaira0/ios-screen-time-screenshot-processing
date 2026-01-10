import { useEffect } from "react";
import { useSearchParams, useParams, useNavigate } from "react-router";
import { Layout } from "@/components/layout/Layout";
import { AnnotationWorkspace } from "@/components/annotation/AnnotationWorkspace";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { useRequireAuth } from "@/hooks/useAuth";
import { PROCESSING_STATUSES, type ProcessingStatus } from "@/types";
import type { VerificationFilterType } from "@/store/slices/types";

const VALID_STATUSES = new Set<string>(Object.values(PROCESSING_STATUSES));
const VALID_FILTERS = new Set<string>(["all", "verified_by_me", "not_verified_by_me", "verified_by_others", "totals_mismatch"]);
const LS_KEY = "annotate-last-params";

export const AnnotationPage = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const groupId = searchParams.get("group") || undefined;
  const rawStatus = searchParams.get("processing_status");
  const processingStatus = (rawStatus && VALID_STATUSES.has(rawStatus) ? rawStatus : undefined) as ProcessingStatus | undefined;
  const initialScreenshotId = id ? parseInt(id, 10) : undefined;
  const rawFilter = searchParams.get("filter");
  const initialFilter = (rawFilter && VALID_FILTERS.has(rawFilter) ? rawFilter : undefined) as VerificationFilterType | undefined;

  useRequireAuth();

  // Restore last-used params when landing on bare /annotate
  useEffect(() => {
    if (!groupId && !processingStatus && !initialScreenshotId) {
      const saved = localStorage.getItem(LS_KEY);
      if (saved) {
        navigate(`/annotate?${saved}`, { replace: true });
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Save current params whenever they change
  useEffect(() => {
    if (groupId || processingStatus) {
      const parts: string[] = [];
      if (groupId) parts.push(`group=${encodeURIComponent(groupId)}`);
      if (processingStatus) parts.push(`processing_status=${encodeURIComponent(processingStatus)}`);
      localStorage.setItem(LS_KEY, parts.join("&"));
    }
  }, [groupId, processingStatus]);

  return (
    <Layout noScroll>
      <ErrorBoundary>
        <AnnotationWorkspace
          groupId={groupId}
          processingStatus={processingStatus}
          initialScreenshotId={initialScreenshotId}
          initialFilter={initialFilter}
        />
      </ErrorBoundary>
    </Layout>
  );
};
