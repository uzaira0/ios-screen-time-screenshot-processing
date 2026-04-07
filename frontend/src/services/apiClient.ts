/**
 * Type-safe API client using openapi-fetch
 * Auto-generated types from OpenAPI schema ensure compile-time type safety
 *
 * IMPORTANT: All types come from the Pydantic schemas via OpenAPI generation.
 * DO NOT define duplicate types here - use components["schemas"]["TypeName"] instead.
 */

import createClient from "openapi-fetch";
import type { paths, components } from "@/types/api-schema";
import { config } from "@/config";

// Re-export types from OpenAPI schema for convenience
export type GroupVerificationSummary = components["schemas"]["GroupVerificationSummary"];
export type ScreenshotTierItem = components["schemas"]["ScreenshotTierItem"];
export type ScreenshotComparison = components["schemas"]["ScreenshotComparison"];
export type VerifierAnnotation = components["schemas"]["VerifierAnnotation"];
export type FieldDifference = components["schemas"]["FieldDifference"];
export type DeleteGroupResponse = components["schemas"]["DeleteGroupResponse"];
export type ResolveDisputeResponse = components["schemas"]["ResolveDisputeResponse"];

// OpenAPI paths in the generated schema already include "/api/v1" prefix
// (e.g., "/api/v1/auth/login", "/api/v1/screenshots/next")
// Therefore, baseUrl should be the app prefix only (e.g., "/screenshot").
//
// config.basePath is the app prefix (e.g., "/ios-screen-time-screenshot-processing")
// config.apiBaseUrl is the full API path (e.g., "/ios-screen-time-screenshot-processing/api/v1")
const API_BASE_URL = config.basePath;

// For image URLs that need the full prefix
const LEGACY_API_PREFIX = config.apiBaseUrl;

// Create type-safe client
export const apiClient = createClient<paths>({ baseUrl: API_BASE_URL });

// Add request interceptor for authentication
// Sends both X-Username and X-Site-Password headers on all requests
apiClient.use({
  onRequest({ request }) {
    const username = localStorage.getItem("username");
    if (username) {
      request.headers.set("X-Username", username);
    }

    const sitePassword = localStorage.getItem("sitePassword");
    if (sitePassword) {
      request.headers.set("X-Site-Password", sitePassword);
    }

    // Debug logging (will appear in browser console)
    if (config.isDev) {
      console.log("[apiClient] Request:", request.url, {
        hasUsername: !!username,
        hasSitePassword: !!sitePassword,
      });
    }

    return request;
  },
  onResponse({ response }) {
    // Handle 401 responses by clearing auth state
    // Only in server mode — WASM/Tauri mode has no server to 401
    // Only logout if not already on login page (prevents redirect loops)
    // and if we're not checking auth status (prevents logout during initial auth check)
    if (response.status === 401 && !config.isLocalMode) {
      const isLoginPage = window.location.pathname.endsWith("/login");
      const isAuthStatusCheck = response.url.includes("/auth/status");

      if (!isLoginPage && !isAuthStatusCheck) {
        console.warn("[apiClient] 401 response - logging out user");
        // Import dynamically to avoid circular dependency
        import("@/store/authStore").then(({ useAuthStore }) => {
          useAuthStore.getState().logout();
        });
        import("react-hot-toast").then(({ default: toast }) => {
          toast.error("Session expired — please log in again", { duration: 5000 });
        });
      }
    }
    return response;
  },
});

/**
 * Build auth headers for raw fetch calls.
 * Only includes headers when values are present (unlike `|| ""` which sends empty strings).
 */
export function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const username = localStorage.getItem("username");
  if (username) headers["X-Username"] = username;
  const sitePassword = localStorage.getItem("sitePassword");
  if (sitePassword) headers["X-Site-Password"] = sitePassword;
  return headers;
}

/**
 * Wrapper around fetch that adds auth headers and handles errors consistently.
 * Used for endpoints not yet in the OpenAPI schema.
 */
async function authFetch(
  url: string,
  init?: RequestInit,
  errorMessage?: string,
): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...init,
    headers: {
      ...getAuthHeaders(),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = errorMessage || "Request failed";
    try {
      const text = await response.text();
      // Try to parse as JSON error envelope
      const json = JSON.parse(text);
      message = json?.detail || json?.error?.message || json?.error || message;
    } catch {
      // HTML or non-JSON response (e.g., nginx 502) — use status text
      message = `Server error (${response.status})`;
    }
    throw new Error(typeof message === "string" ? message : `Server error (${response.status})`);
  }
  return response;
}

/**
 * Helper function to throw errors with backend detail messages
 */
function throwIfError(
  error: unknown,
  defaultMessage: string,
): asserts error is undefined {
  if (error) {
    const errObj = error as { detail?: string; error?: string | { message?: string; code?: string } };
    // Handle nested error envelope: { error: { code: "...", message: "..." } }
    const errorField = errObj?.error;
    const errorMsg = typeof errorField === "string" ? errorField : errorField?.message;
    // Rate limiting has a specific user-friendly message
    const isRateLimit = typeof errorMsg === "string" && errorMsg.includes("Rate limit");
    const detail = errObj?.detail
      || (isRateLimit ? "Too many requests — please wait a moment and try again" : null)
      || errorMsg
      || defaultMessage;
    throw new Error(detail);
  }
}

/**
 * Type-safe API wrapper functions
 * These provide a clean interface for the application
 */
export const api = {
  // Authentication
  auth: {
    async isPasswordRequired(): Promise<boolean> {
      const { data, error } = await apiClient.GET("/api/v1/auth/status");
      if (error) {
        console.warn("Failed to check password requirement:", error);
        return false;
      }
      return data?.password_required ?? false;
    },

    async login(username: string, password?: string) {
      const { data, error } = await apiClient.POST("/api/v1/auth/login", {
        body: { username, password: password || null },
      });
      throwIfError(error, "Login failed");
      return data;
    },

    async getMe() {
      const { data, error } = await apiClient.GET("/api/v1/auth/me");
      throwIfError(error, "Failed to get current user");
      return data;
    },
  },

  // Screenshots
  screenshots: {
    async getNext(params?: { group?: string; processing_status?: string }) {
      const { data, error } = await apiClient.GET("/api/v1/screenshots/next", {
        params: { query: params ?? {} },
      });
      throwIfError(error, "Failed to get next screenshot");
      return data;
    },

    async getById(id: number) {
      const { data, error } = await apiClient.GET(
        "/api/v1/screenshots/{screenshot_id}",
        {
          params: { path: { screenshot_id: id } },
        },
      );
      throwIfError(error, "Failed to get screenshot");
      return data;
    },

    async getStats() {
      const { data, error } = await apiClient.GET("/api/v1/screenshots/stats");
      throwIfError(error, "Failed to get stats");
      return data;
    },

    async list(params?: {
      page?: number;
      page_size?: number;
      group_id?: string;
      processing_status?: string;
      verified_by_me?: boolean;
      verified_by_others?: boolean;
      search?: string;
      totals_mismatch?: boolean;
      sort_by?: string;
      sort_order?: string;
    }) {
      const { data, error } = await apiClient.GET("/api/v1/screenshots/list", {
        params: { query: params ?? {} },
      });
      throwIfError(error, "Failed to list screenshots");
      return data;
    },

    async skip(id: number) {
      const { error } = await apiClient.POST(
        "/api/v1/screenshots/{screenshot_id}/skip",
        {
          params: { path: { screenshot_id: id } },
        },
      );
      throwIfError(error, "Failed to skip screenshot");
    },

    async verify(id: number, gridCoords?: { upper_left: { x: number; y: number }; lower_right: { x: number; y: number } }) {
      const { data, error } = await apiClient.POST(
        "/api/v1/screenshots/{screenshot_id}/verify",
        {
          params: { path: { screenshot_id: id } },
          body: gridCoords
            ? {
                grid_upper_left_x: gridCoords.upper_left.x,
                grid_upper_left_y: gridCoords.upper_left.y,
                grid_lower_right_x: gridCoords.lower_right.x,
                grid_lower_right_y: gridCoords.lower_right.y,
              }
            : undefined,
        },
      );
      throwIfError(error, "Failed to verify screenshot");
      return data;
    },

    async unverify(id: number) {
      const { data, error } = await apiClient.DELETE(
        "/api/v1/screenshots/{screenshot_id}/verify",
        {
          params: { path: { screenshot_id: id } },
        },
      );
      throwIfError(error, "Failed to unverify screenshot");
      return data;
    },

    async getImageUrl(id: number): Promise<string> {
      return `${LEGACY_API_PREFIX}/screenshots/${id}/image`;
    },

    async reprocess(
      id: number,
      options?: {
        grid_upper_left_x?: number;
        grid_upper_left_y?: number;
        grid_lower_right_x?: number;
        grid_lower_right_y?: number;
        processing_method?: "ocr_anchored" | "line_based";
        max_shift?: number;
      },
    ) {
      const { data, error } = await apiClient.POST(
        "/api/v1/screenshots/{screenshot_id}/reprocess",
        {
          params: { path: { screenshot_id: id } },
          body: { max_shift: 5, ...options },
        },
      );
      throwIfError(error, "Failed to reprocess screenshot");
      return data;
    },

    async navigate(
      id: number,
      params: {
        group_id?: string;
        processing_status?: string;
        verified_by_me?: boolean;
        verified_by_others?: boolean;
        totals_mismatch?: boolean;
        direction?: "next" | "prev" | "current";
      },
    ) {
      const { data, error } = await apiClient.GET(
        "/api/v1/screenshots/{screenshot_id}/navigate",
        {
          params: {
            path: { screenshot_id: id },
            query: params,
          },
        },
      );
      throwIfError(error, "Failed to navigate screenshots");
      return data;
    },

    async update(
      id: number,
      updates: {
        extracted_title?: string | null;
        extracted_hourly_data?: Record<string, number> | null;
      },
    ) {
      const { data, error } = await apiClient.PATCH(
        "/api/v1/screenshots/{screenshot_id}",
        {
          params: { path: { screenshot_id: id } },
          body: updates,
        },
      );
      throwIfError(error, "Failed to update screenshot");
      return data;
    },

    async recalculateOcr(id: number) {
      const { data, error } = await apiClient.POST(
        "/api/v1/screenshots/{screenshot_id}/recalculate-ocr",
        {
          params: { path: { screenshot_id: id } },
        },
      );
      throwIfError(error, "Failed to recalculate OCR");
      return data;
    },
  },

  // Annotations
  annotations: {
    async create(annotation: components["schemas"]["AnnotationCreate"]) {
      const { data, error } = await apiClient.POST("/api/v1/annotations/", {
        body: annotation,
      });
      throwIfError(error, "Failed to create annotation");
      return data;
    },

    async getHistory(params?: { skip?: number; limit?: number }) {
      const { data, error } = await apiClient.GET(
        "/api/v1/annotations/history",
        {
          params: { query: params ?? {} },
        },
      );
      throwIfError(error, "Failed to get annotation history");
      return data;
    },

    async delete(id: number) {
      const { error } = await apiClient.DELETE(
        "/api/v1/annotations/{annotation_id}",
        {
          params: { path: { annotation_id: id } },
        },
      );
      throwIfError(error, "Failed to delete annotation");
    },
  },

  // Consensus
  consensus: {
    async getForScreenshot(id: number) {
      const { data, error } = await apiClient.GET(
        "/api/v1/consensus/{screenshot_id}",
        {
          params: { path: { screenshot_id: id } },
        },
      );
      throwIfError(error, "Failed to get consensus");
      return data;
    },

    async getSummary() {
      const { data, error } = await apiClient.GET(
        "/api/v1/consensus/summary/stats",
      );
      throwIfError(error, "Failed to get consensus summary");
      return data;
    },

    // Verification tier endpoints - using typed apiClient
    async getGroupsWithTiers(): Promise<GroupVerificationSummary[]> {
      const { data, error } = await apiClient.GET("/api/v1/consensus/groups");
      throwIfError(error, "Failed to get groups with verification tiers");
      return data!;
    },

    async getScreenshotsByTier(
      groupId: string,
      tier: "single_verified" | "agreed" | "disputed",
    ): Promise<ScreenshotTierItem[]> {
      const { data, error } = await apiClient.GET(
        "/api/v1/consensus/groups/{group_id}/screenshots",
        {
          params: {
            path: { group_id: groupId },
            query: { tier },
          },
        },
      );
      throwIfError(error, "Failed to get screenshots by tier");
      return data!;
    },

    async getScreenshotComparison(
      screenshotId: number,
    ): Promise<ScreenshotComparison> {
      const { data, error } = await apiClient.GET(
        "/api/v1/consensus/screenshots/{screenshot_id}/compare",
        {
          params: { path: { screenshot_id: screenshotId } },
        },
      );
      throwIfError(error, "Failed to get screenshot comparison");
      return data!;
    },

    async resolveDispute(
      screenshotId: number,
      resolution: {
        hourly_values: Record<string, number>;
        extracted_title?: string;
        extracted_total?: string;
        resolution_notes?: string;
      },
    ): Promise<ResolveDisputeResponse> {
      const { data, error } = await apiClient.POST(
        "/api/v1/consensus/screenshots/{screenshot_id}/resolve",
        {
          params: { path: { screenshot_id: screenshotId } },
          body: resolution,
        },
      );
      throwIfError(error, "Failed to resolve dispute");
      return data!;
    },
  },

  // Groups
  groups: {
    async list() {
      const { data, error } = await apiClient.GET("/api/v1/screenshots/groups");
      throwIfError(error, "Failed to list groups");
      return data;
    },

    async getById(id: string) {
      const { data, error } = await apiClient.GET(
        "/api/v1/screenshots/groups/{group_id}",
        {
          params: { path: { group_id: id } },
        },
      );
      throwIfError(error, "Failed to get group");
      return data;
    },
  },

  // Admin
  admin: {
    async getUsers() {
      const { data, error } = await apiClient.GET("/api/v1/admin/users");
      throwIfError(error, "Failed to get users");
      return data;
    },

    async updateUser(
      id: number,
      updates: { is_active?: boolean; role?: string },
    ) {
      const { data, error } = await apiClient.PUT(
        "/api/v1/admin/users/{user_id}",
        {
          params: {
            path: { user_id: id },
            query: updates,
          },
        },
      );
      throwIfError(error, "Failed to update user");
      return data;
    },

    async resetTestData() {
      const { data, error } = await apiClient.POST(
        "/api/v1/admin/reset-test-data",
      );
      throwIfError(error, "Failed to reset test data");
      return data;
    },

    async deleteGroup(groupId: string): Promise<DeleteGroupResponse> {
      const { data, error } = await apiClient.DELETE(
        "/api/v1/admin/groups/{group_id}",
        {
          params: { path: { group_id: groupId } },
        },
      );
      throwIfError(error, "Failed to delete group");
      return data!;
    },
  },

  // Preprocessing (server-only, no DI needed)
  preprocessing: {
    async getDetails(id: number) {
      const { data, error } = await apiClient.GET(
        "/api/v1/screenshots/{screenshot_id}/preprocessing",
        {
          params: { path: { screenshot_id: id } },
        },
      );
      throwIfError(error, "Failed to get preprocessing details");
      return data;
    },

    async preprocess(
      id: number,
      options: {
        phi_pipeline_preset?: string;
        phi_redaction_method?: string;
        phi_detection_enabled?: boolean;
        phi_ocr_engine?: string;
        phi_ner_detector?: string;
        run_ocr_after?: boolean;
      },
    ) {
      const { data, error } = await apiClient.POST(
        "/api/v1/screenshots/{screenshot_id}/preprocess",
        {
          params: { path: { screenshot_id: id } },
          body: {
            phi_pipeline_preset: options.phi_pipeline_preset ?? "screen_time",
            phi_redaction_method: options.phi_redaction_method ?? "redbox",
            phi_detection_enabled: options.phi_detection_enabled ?? true,
            phi_ocr_engine: (options.phi_ocr_engine ?? "leptess") as "pytesseract" | "leptess",
            phi_ner_detector: (options.phi_ner_detector ?? "presidio") as "presidio" | "gliner",
            run_ocr_after: options.run_ocr_after ?? false,
          },
        },
      );
      throwIfError(error, "Failed to queue preprocessing");
      return data;
    },

    async preprocessBatch(request: {
      group_id: string;
      screenshot_ids?: number[];
      phi_pipeline_preset?: string;
      phi_redaction_method?: string;
      phi_detection_enabled?: boolean;
      phi_ocr_engine?: string;
      phi_ner_detector?: string;
      run_ocr_after?: boolean;
    }) {
      const { data, error } = await apiClient.POST(
        "/api/v1/screenshots/preprocess-batch",
        {
          body: {
            group_id: request.group_id,
            screenshot_ids: request.screenshot_ids ?? null,
            phi_pipeline_preset:
              request.phi_pipeline_preset ?? "screen_time",
            phi_redaction_method: request.phi_redaction_method ?? "redbox",
            phi_detection_enabled: request.phi_detection_enabled ?? true,
            phi_ocr_engine: (request.phi_ocr_engine ?? "leptess") as "pytesseract" | "leptess",
            phi_ner_detector: (request.phi_ner_detector ?? "presidio") as "presidio" | "gliner",
            run_ocr_after: request.run_ocr_after ?? false,
          },
        },
      );
      throwIfError(error, "Failed to queue batch preprocessing");
      return data;
    },

    // --- Composable pipeline endpoints ---

    async runStage(
      stage: string,
      options: {
        group_id?: string;
        screenshot_ids?: number[];
        phi_pipeline_preset?: string;
        phi_redaction_method?: string;
        phi_ocr_engine?: string;
        phi_ner_detector?: string;
        llm_endpoint?: string;
        llm_model?: string;
        llm_api_key?: string;
        ocr_method?: string;
      },
    ) {
      const stageUrlMap: Record<string, string> = {
        device_detection: "/api/v1/screenshots/preprocess-stage/device-detection",
        cropping: "/api/v1/screenshots/preprocess-stage/cropping",
        phi_detection: "/api/v1/screenshots/preprocess-stage/phi-detection",
        phi_redaction: "/api/v1/screenshots/preprocess-stage/phi-redaction",
        ocr: "/api/v1/screenshots/preprocess-stage/ocr",
      };
      const url = stageUrlMap[stage];
      if (!url) throw new Error(`Unknown stage: ${stage}`);

      // Build request body based on stage
      const body: Record<string, unknown> = {
        screenshot_ids: options.screenshot_ids ?? null,
        group_id: options.group_id ?? null,
      };
      if (stage === "phi_detection") {
        body.phi_pipeline_preset = options.phi_pipeline_preset ?? "screen_time";
        body.phi_ocr_engine = options.phi_ocr_engine ?? "leptess";
        body.phi_ner_detector = options.phi_ner_detector ?? "presidio";
        if (options.llm_endpoint) body.llm_endpoint = options.llm_endpoint;
        if (options.llm_model) body.llm_model = options.llm_model;
        if (options.llm_api_key) body.llm_api_key = options.llm_api_key;
      }
      if (stage === "phi_redaction") {
        body.phi_redaction_method = options.phi_redaction_method ?? "redbox";
      }
      if (stage === "ocr") {
        body.ocr_method = options.ocr_method ?? "line_based";
      }

      const response = await authFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }, "Failed to queue stage");
      return response.json();
    },

    async cancelPhiDetection(taskIds: string[], groupId?: string) {
      const response = await authFetch(
        "/api/v1/screenshots/preprocess-stage/phi-detection/cancel",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task_ids: taskIds, group_id: groupId ?? null }),
        },
        "Failed to cancel PHI detection",
      );
      return response.json();
    },

    async resetStage(stage: string, groupId: string) {
      const response = await authFetch(
        "/api/v1/screenshots/preprocess-stage/reset",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stage, group_id: groupId }),
        },
        "Failed to reset stage",
      );
      return response.json();
    },

    async invalidateFromStage(screenshotId: number, stage: string) {
      const response = await authFetch(
        `/api/v1/screenshots/${screenshotId}/invalidate-from-stage`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stage }),
        },
        "Failed to invalidate stages",
      );
      return response.json();
    },

    async getSummary(groupId: string) {
      const response = await authFetch(
        `/api/v1/screenshots/preprocessing-summary?group_id=${encodeURIComponent(groupId)}`,
        undefined,
        "Failed to get preprocessing summary",
      );
      return response.json();
    },

    async getEventLog(screenshotId: number) {
      const response = await authFetch(
        `/api/v1/screenshots/${screenshotId}/preprocessing-events`,
        undefined,
        "Failed to get event log",
      );
      return response.json();
    },

    async uploadBrowser(formData: FormData) {
      const response = await authFetch(
        "/api/v1/screenshots/upload/browser",
        { method: "POST", body: formData },
        "Failed to upload",
      );
      return response.json();
    },

    async getOriginalImageUrl(screenshotId: number): Promise<string> {
      return `${LEGACY_API_PREFIX}/screenshots/${screenshotId}/original-image`;
    },

    async applyManualCrop(
      screenshotId: number,
      crop: { left: number; top: number; right: number; bottom: number },
    ) {
      const response = await authFetch(
        `/api/v1/screenshots/${screenshotId}/manual-crop`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(crop),
        },
        "Failed to apply crop",
      );
      return response.json();
    },

    async getPHIRegions(screenshotId: number) {
      const response = await authFetch(
        `/api/v1/screenshots/${screenshotId}/phi-regions`,
        undefined,
        "Failed to get PHI regions",
      );
      return response.json();
    },

    async savePHIRegions(
      screenshotId: number,
      body: { regions: Array<{ x: number; y: number; w: number; h: number; label: string; source: string; confidence: number; text: string }>; preset: string },
    ) {
      const response = await authFetch(
        `/api/v1/screenshots/${screenshotId}/phi-regions`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        "Failed to save PHI regions",
      );
      return response.json();
    },

    async applyRedaction(
      screenshotId: number,
      body: { regions: Array<{ x: number; y: number; w: number; h: number; label: string; source: string; confidence: number; text: string }>; redaction_method: string },
    ) {
      const response = await authFetch(
        `/api/v1/screenshots/${screenshotId}/apply-redaction`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        "Failed to apply redaction",
      );
      return response.json();
    },

    async getPhiWhitelist(): Promise<{ whitelist: string[] }> {
      const response = await authFetch(
        "/api/v1/screenshots/phi-text-whitelist",
        undefined,
        "Failed to get PHI whitelist",
      );
      return response.json();
    },

    async addToPhiWhitelist(text: string): Promise<{ whitelist: string[] }> {
      const response = await authFetch(
        "/api/v1/screenshots/phi-text-whitelist",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        },
        "Failed to add to PHI whitelist",
      );
      return response.json();
    },

    async removeFromPhiWhitelist(text: string): Promise<{ whitelist: string[] }> {
      const response = await authFetch(
        "/api/v1/screenshots/phi-text-whitelist",
        {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        },
        "Failed to remove from PHI whitelist",
      );
      return response.json();
    },
  },

  // Export
  export: {
    getCSVUrl(groupId?: string): string {
      const params = groupId ? `?group_id=${groupId}` : "";
      return `${LEGACY_API_PREFIX}/screenshots/export/csv${params}`;
    },
  },
};

export default api;
