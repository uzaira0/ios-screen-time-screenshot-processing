/**
 * @deprecated Import from '@/types' instead.
 *
 * This file re-exports types for backward compatibility.
 * All types are now derived from the OpenAPI schema in src/types/index.ts.
 *
 * Migration: Replace `import { X } from '@/core/models'` with `import { X } from '@/types'`
 */

// Re-export everything from the canonical types location
export * from "@/types";

// Legacy constant export for backward compatibility
export const ImageType = {
  BATTERY: "battery",
  SCREEN_TIME: "screen_time",
} as const;
