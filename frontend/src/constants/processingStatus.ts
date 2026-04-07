/**
 * Processing statuses shown as filter buttons in the preprocessing UI.
 * This is a SUBSET of the full ProcessingStatus type from types/index.ts.
 * "processing" and "deleted" are excluded because they are transient/hidden states.
 */

export const FILTER_STATUSES = ['pending', 'completed', 'failed', 'skipped'] as const;

export type FilterStatus = typeof FILTER_STATUSES[number];

/**
 * Human-readable labels for filter statuses
 */
export const FILTER_STATUS_LABELS: Record<FilterStatus, string> = {
  pending: 'Pending',
  completed: 'Preprocessed',
  failed: 'Failed',
  skipped: 'Skipped',
};

/**
 * Colors for processing status badges
 */
export const FILTER_STATUS_COLORS: Record<FilterStatus, string> = {
  pending: 'text-primary-600 bg-primary-50',
  completed: 'text-green-600 bg-green-50',
  failed: 'text-red-600 bg-red-50',
  skipped: 'text-slate-600 bg-slate-100',
};
