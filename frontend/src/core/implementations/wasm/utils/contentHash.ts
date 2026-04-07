/**
 * Compute SHA-256 content hash for deduplication.
 * Returns null if crypto.subtle is unavailable (non-secure context),
 * signaling that dedup should be skipped rather than matching on empty strings.
 */
export async function computeContentHash(blob: Blob): Promise<string | null> {
  if (!crypto?.subtle) {
    // crypto.subtle requires a secure context (HTTPS or localhost)
    return null;
  }
  const buf = await blob.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
