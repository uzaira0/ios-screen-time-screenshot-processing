/**
 * Try to parse a date string from a folder name into yyyy-MM-dd format.
 * Handles many variations:
 *   "2024-01-15"           → "2024-01-15"
 *   "2024_01_15"           → "2024-01-15"
 *   "01-15-2024"           → "2024-01-15"
 *   "01.15.2024"           → "2024-01-15"
 *   "10.25.2024"           → "2024-10-25"
 *   "Day 10 10.25.2024"    → "2024-10-25"
 *   "Day 10 10-25-2024"    → "2024-10-25"
 *   "Day_3_01.02.2025"     → "2025-01-02"
 *   "2024-Jan-15"          → "2024-01-15"
 *   "Jan 15, 2024"         → "2024-01-15"
 *   "15 Jan 2024"          → "2024-01-15"
 *   "January 15, 2024"     → "2024-01-15"
 *   "7.18.23"              → "2023-07-18"
 *   "Day 1 7.18.23"        → "2023-07-18"
 * Returns "" if no date can be extracted.
 */
function parseDateFromFolder(raw: string): string {
  if (!raw) return "";

  const MONTHS: Record<string, string> = {
    jan: "01", january: "01", feb: "02", february: "02", mar: "03", march: "03",
    apr: "04", april: "04", may: "05", jun: "06", june: "06",
    jul: "07", july: "07", aug: "08", august: "08", sep: "09", september: "09",
    oct: "10", october: "10", nov: "11", november: "11", dec: "12", december: "12",
  };

  const pad = (n: number) => String(n).padStart(2, "0");
  const s = raw.trim();

  // Already yyyy-MM-dd
  let m = s.match(/(\d{4})[-_](\d{1,2})[-_](\d{1,2})/);
  if (m) return `${m[1]}-${pad(+m[2]!)}-${pad(+m[3]!)}`;

  // yyyy-Mon-dd or yyyy-Month-dd
  m = s.match(/(\d{4})[-_ ]([A-Za-z]+)[-_ ](\d{1,2})/);
  if (m && MONTHS[m[2]!.toLowerCase()]) {
    return `${m[1]}-${MONTHS[m[2]!.toLowerCase()]}-${pad(+m[3]!)}`;
  }

  // MM.DD.YYYY or MM-DD-YYYY or MM/DD/YYYY (possibly embedded in a longer string like "Day 10 10.25.2024")
  // Also handles 2-digit years: "7.18.23" → 2023-07-18
  m = s.match(/(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})/);
  if (m) {
    const a = +m[1]!, b = +m[2]!;
    let year = +m[3]!;
    // Expand 2-digit year: 00-49 → 2000s, 50-99 → 1900s
    if (year < 100) year += year < 50 ? 2000 : 1900;
    // Disambiguate: if a > 12, it's DD.MM.YYYY; otherwise assume MM.DD.YYYY (US convention)
    if (a > 12 && b <= 12) return `${year}-${pad(b)}-${pad(a)}`;
    if (a <= 12) return `${year}-${pad(a)}-${pad(b)}`;
    return `${year}-${pad(a)}-${pad(b)}`;
  }

  // Mon DD, YYYY or Month DD, YYYY (also 2-digit year)
  m = s.match(/([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{2,4})/);
  if (m && MONTHS[m[1]!.toLowerCase()]) {
    let year = +m[3]!;
    if (year < 100) year += year < 50 ? 2000 : 1900;
    return `${year}-${MONTHS[m[1]!.toLowerCase()]}-${pad(+m[2]!)}`;
  }

  // DD Mon YYYY or DD Month YYYY (also 2-digit year)
  m = s.match(/(\d{1,2})\s+([A-Za-z]+)\s+(\d{2,4})/);
  if (m && MONTHS[m[2]!.toLowerCase()]) {
    let year = +m[3]!;
    if (year < 100) year += year < 50 ? 2000 : 1900;
    return `${year}-${MONTHS[m[2]!.toLowerCase()]}-${pad(+m[1]!)}`;
  }

  return "";
}

export interface ParsedFilePath {
  participant_id: string;
  screenshot_date: string;
  filename: string;
  original_filepath: string;
  /** Top-level folder from webkitRelativePath (study/root folder name) */
  root_folder: string;
}

/**
 * Parse webkitRelativePath to extract participant_id, date, and filename.
 * Patterns:
 *   root/participant_id/date/filename.png → all fields
 *   participant_id/date/filename.png → participant_id as root
 *   participant_id/filename.png → participant + filename
 *   filename.png → "unknown" participant
 */
export function parseRelativePath(file: File): ParsedFilePath {
  const relativePath = file.webkitRelativePath || file.name;
  const parts = relativePath.split("/").filter(Boolean);

  if (parts.length >= 3) {
    return {
      root_folder: parts[0]!,
      participant_id: parts[parts.length - 3]!,
      screenshot_date: parseDateFromFolder(parts[parts.length - 2]!),
      filename: parts[parts.length - 1]!,
      original_filepath: relativePath,
    };
  } else if (parts.length === 2) {
    return {
      root_folder: parts[0]!,
      participant_id: parts[0]!,
      screenshot_date: "",
      filename: parts[1]!,
      original_filepath: relativePath,
    };
  } else {
    return {
      root_folder: "",
      participant_id: "unknown",
      screenshot_date: "",
      filename: file.name,
      original_filepath: file.name,
    };
  }
}

export function isImageFile(file: File): boolean {
  return file.type === "image/png" || file.type === "image/jpeg" || file.name.endsWith(".png") || file.name.endsWith(".jpg") || file.name.endsWith(".jpeg");
}
