export const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

export const formatRelativeTime = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return formatDate(dateString);
};

export const formatMinutes = (minutes: number): string => {
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);

  if (hours === 0) return `${mins}m`;
  if (mins === 0) return `${hours}h`;
  return `${hours}h ${mins}m`;
};

export const calculateTotalMinutes = (hourlyData: Record<string | number, number>): number => {
  return Object.values(hourlyData).reduce((sum, val) => sum + val, 0);
};

export const formatPercentage = (value: number): string => {
  return `${Math.round(value * 100)}%`;
};

/**
 * Check if bar total and OCR total have a meaningful mismatch.
 * Uses a 10% or 5-minute threshold (whichever is larger).
 * Returns false if either value is null/missing.
 */
export function hasTotalsMismatchByThreshold(barTotal: number, ocrMinutes: number | null): boolean {
  if (ocrMinutes === null || ocrMinutes <= 0) return false;
  return Math.abs(barTotal - ocrMinutes) > Math.max(ocrMinutes * 0.1, 5);
}

/** Parse an OCR total string like "1h 31m", "45m", "2h" into total minutes. */
export function parseOcrTotalMinutes(ocrTotal: string | null | undefined): number | null {
  if (!ocrTotal) return null;
  let minutes = 0;
  const hMatch = ocrTotal.match(/(\d+)\s*h/i);
  const mMatch = ocrTotal.match(/(\d+)\s*m/i);
  if (hMatch) minutes += parseInt(hMatch[1]!, 10) * 60;
  if (mMatch) minutes += parseInt(mMatch[1]!, 10);
  if (minutes === 0 && !hMatch && !mMatch) return null;
  return minutes;
}
