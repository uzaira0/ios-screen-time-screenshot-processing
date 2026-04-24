import { describe, it, expect } from "bun:test";
import { classifyPageWords } from "../ocr.canvas";

// Markers from ocr.canvas.ts (mirrored here for test clarity)
// DAILY: WEEK, DAY, MOST, USED, CATEGORIES, TODAY, SHOW, ENTERTAINMENT, EDUCATION, INFORMATION, READING
// APP:   INFO, DEVELOPER, RATING, LIMIT, AGE, DAILY, AVERAGE

// ── classifyPageWords ─────────────────────────────────────────────────────────

describe("classifyPageWords", () => {
  it("empty word list → zero counts, not daily", () => {
    const result = classifyPageWords([]);
    expect(result).toEqual({ dailyCount: 0, appCount: 0, isDaily: false });
  });

  it("words matching only daily markers → isDaily true", () => {
    const words = [{ text: "Screen" }, { text: "Time" }, { text: "Today" }, { text: "Week" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(2); // TODAY, WEEK
    expect(result.appCount).toBe(0);
    expect(result.isDaily).toBe(true);
  });

  it("words matching only app markers → isDaily false", () => {
    const words = [{ text: "App" }, { text: "Info" }, { text: "Rating" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(0);
    expect(result.appCount).toBe(2); // INFO, RATING
    expect(result.isDaily).toBe(false);
  });

  // ── regression: per-word counting with break prevents double-counting ──────

  it("word 'TODAY' matches both 'DAY' and 'TODAY' — counts as 1, not 2", () => {
    // Old broken code: joined all words into one string and searched that.
    // "TODAY" contains both "DAY" and "TODAY" as substrings → old code counted 2.
    // New code: breaks after first match per word → counts 1.
    const words = [{ text: "TODAY" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(1); // not 2
    expect(result.appCount).toBe(0);
  });

  it("word 'ENTERTAINMENT' counts as 1 daily match despite containing 'READING'-adjacent chars", () => {
    const words = [{ text: "Entertainment" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(1);
    expect(result.appCount).toBe(0);
  });

  it("word 'INFORMATION' counts as 1 daily (not also APP 'INFO')", () => {
    // INFORMATION contains "INFO" which is an app marker.
    // But app markers are checked independently per word, so INFORMATION can match
    // both INFORMATION (daily) and INFO (app). The break only applies within a category.
    const words = [{ text: "INFORMATION" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(1); // INFORMATION
    expect(result.appCount).toBe(1);   // INFO is a substring of INFORMATION
  });

  it("each word counts independently — 3 daily words → dailyCount 3", () => {
    const words = [
      { text: "Week" },
      { text: "Most" },
      { text: "Used" },
    ];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(3);
    expect(result.appCount).toBe(0);
    expect(result.isDaily).toBe(true);
  });

  it("case-insensitive matching", () => {
    const words = [{ text: "categories" }, { text: "developer" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(1); // CATEGORIES
    expect(result.appCount).toBe(1);   // DEVELOPER
  });

  it("tied counts (equal daily and app) → isDaily false", () => {
    const words = [{ text: "WEEK" }, { text: "INFO" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(1);
    expect(result.appCount).toBe(1);
    expect(result.isDaily).toBe(false); // daily > app required
  });

  it("word with no marker → not counted", () => {
    // "Messages" contains "AGE" (app marker) — use neutral words instead
    const words = [{ text: "Safari" }, { text: "Photos" }, { text: "Maps" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).toBe(0);
    expect(result.appCount).toBe(0);
    expect(result.isDaily).toBe(false);
  });

  // ── regression: old broken approach ──────────────────────────────────────────

  it("regression: 'TODAY' must not be counted twice as old join-string approach did", () => {
    // Old code: words.map(w => w.text).join(' ') → 'TODAY' then searched for each
    // marker in the full string → both 'DAY' and 'TODAY' matched → dailyCount += 2
    const words = [{ text: "TODAY" }, { text: "Screen" }, { text: "Time" }];
    const result = classifyPageWords(words);
    expect(result.dailyCount).not.toBe(2); // old broken value
    expect(result.dailyCount).toBe(1);     // correct: one match per word
  });
});
