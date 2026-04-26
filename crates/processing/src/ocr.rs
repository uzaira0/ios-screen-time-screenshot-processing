//! OCR text extraction and pattern matching.
//!
//! Port of Python ocr.py — regex patterns for digit normalization,
//! time extraction, and daily total page detection.

#[cfg(feature = "ocr")]
use std::cell::RefCell;

use lazy_static::lazy_static;
use regex::Regex;

// ---------------------------------------------------------------------------
// Thread-local cached LepTess instance — avoids re-loading eng.traineddata
// on every call (saves ~200ms per image).
// ---------------------------------------------------------------------------

#[cfg(feature = "ocr")]
thread_local! {
    static LEPTESS: RefCell<Option<leptess::LepTess>> = RefCell::new(None);
}

/// Get or initialise the thread-local LepTess instance.
#[cfg(feature = "ocr")]
fn with_leptess<F, T>(psm: &str, f: F) -> Result<T, crate::types::ProcessingError>
where
    F: FnOnce(&mut leptess::LepTess) -> Result<T, crate::types::ProcessingError>,
{
    LEPTESS.with(|cell| {
        let mut opt = cell.borrow_mut();
        if opt.is_none() {
            let lt = leptess::LepTess::new(None, "eng").map_err(|e| {
                crate::types::ProcessingError::Ocr(format!("Tesseract init failed: {e}"))
            })?;
            *opt = Some(lt);
        }
        let lt = opt.as_mut().unwrap();
        // PSM may differ per call — set it every time (cheap)
        if lt
            .set_variable(leptess::Variable::TesseditPagesegMode, psm)
            .is_err()
        {
            log::warn!(
                "Failed to set Tesseract PSM to '{}', using previous setting",
                psm
            );
        }
        f(lt)
    })
}

// ---------------------------------------------------------------------------
// Pre-compiled regex patterns for OCR digit normalization
// ---------------------------------------------------------------------------

lazy_static! {
    // 1-like characters: I, l, |
    static ref RE_1_BEFORE_UNIT: Regex = Regex::new(r"([Il|])(\s*[hm]\b)").unwrap();
    static ref RE_1_AFTER_DIGIT: Regex = Regex::new(r"(\d)([Il|])(\s*[hms]\b)").unwrap();
    static ref RE_1_BEFORE_DIGIT: Regex = Regex::new(r"([Il|])(\d)").unwrap();

    // 0-like characters: O
    static ref RE_0_BEFORE_UNIT: Regex = Regex::new(r"([O])(\s*[hms]\b)").unwrap();
    static ref RE_0_AFTER_DIGIT: Regex = Regex::new(r"(\d)([O])(\s*[hms]\b)").unwrap();
    static ref RE_0_BEFORE_DIGIT: Regex = Regex::new(r"([O])(\d)").unwrap();
    static ref RE_0_BETWEEN_DIGITS: Regex = Regex::new(r"(\d)([O])(\d)").unwrap();

    // 4-like characters: A
    static ref RE_4_BEFORE_UNIT: Regex = Regex::new(r"([A])(\s*[hm]\b)").unwrap();
    static ref RE_4_AFTER_DIGIT: Regex = Regex::new(r"(\d)([A])(\s*[hms]\b)").unwrap();

    // 5-like characters: S
    static ref RE_5_BEFORE_UNIT: Regex = Regex::new(r"([S])(\s*[hm]\b)").unwrap();
    static ref RE_5_AFTER_DIGIT: Regex = Regex::new(r"(\d)([S])(\s*[hm]\b)").unwrap();
    static ref RE_5_BEFORE_DIGIT: Regex = Regex::new(r"([S])(\d)").unwrap();

    // 6-like characters: G, b
    static ref RE_6_BEFORE_UNIT: Regex = Regex::new(r"([Gb])(\s*[hms]\b)").unwrap();
    static ref RE_6_AFTER_DIGIT: Regex = Regex::new(r"(\d)([Gb])(\s*[hms]\b)").unwrap();

    // 8-like characters: B
    static ref RE_8_BEFORE_UNIT: Regex = Regex::new(r"([B])(\s*[hms]\b)").unwrap();
    static ref RE_8_AFTER_DIGIT: Regex = Regex::new(r"(\d)([B])(\s*[hms]\b)").unwrap();

    // 9-like characters: g, q
    static ref RE_9_BEFORE_UNIT: Regex = Regex::new(r"([gq])(\s*[hms]\b)").unwrap();
    static ref RE_9_AFTER_DIGIT: Regex = Regex::new(r"(\d)([gq])(\s*[hms]\b)").unwrap();

    // 2-like characters: Z
    static ref RE_2_BEFORE_UNIT: Regex = Regex::new(r"([Z])(\s*[hms]\b)").unwrap();
    static ref RE_2_AFTER_DIGIT: Regex = Regex::new(r"(\d)([Z])(\s*[hms]\b)").unwrap();

    // 7-like characters: T
    static ref RE_7_BEFORE_UNIT: Regex = Regex::new(r"([T])(\s*[hms]\b)").unwrap();
    static ref RE_7_AFTER_DIGIT: Regex = Regex::new(r"(\d)([T])(\s*[hms]\b)").unwrap();

    // Time extraction patterns
    static ref RE_HOUR_MIN: Regex = Regex::new(r"(\d{1,2})\s*h\s*(\d{1,2})\s*m").unwrap();
    // Note: Rust regex doesn't support lookahead. We match broadly and filter in code.
    static ref RE_HOUR_MIN_NO_M: Regex = Regex::new(r"(\d{1,2})\s*h\s+(\d{1,2})(\s*[hms])?").unwrap();
    static ref RE_MIN_SEC: Regex = Regex::new(r"(\d{1,2})\s*m\s*([0O]|\d{1,2})\s*s").unwrap();
    static ref RE_MIN_ONLY: Regex = Regex::new(r"(\d{1,2})\s*m\b").unwrap();
    static ref RE_HOURS_ONLY: Regex = Regex::new(r"(\d{1,2})\s*h\b").unwrap();
    static ref RE_SEC_ONLY: Regex = Regex::new(r"([0O]|\d{1,2})\s*s\b").unwrap();
    static ref RE_HAS_TIME: Regex = Regex::new(r"\d+\s*[hms]").unwrap();
}

/// Normalize common OCR misreadings of digits in time contexts.
///
/// Port of Python `_normalize_ocr_digits()`.
pub fn normalize_ocr_digits(text: &str) -> String {
    let mut result = text.to_string();

    // 1-like: I, l, |
    result = RE_1_BEFORE_UNIT.replace_all(&result, "1$2").to_string();
    result = RE_1_AFTER_DIGIT.replace_all(&result, "${1}1$3").to_string();
    result = RE_1_BEFORE_DIGIT.replace_all(&result, "1$2").to_string();

    // 0-like: O
    result = RE_0_BEFORE_UNIT.replace_all(&result, "0$2").to_string();
    result = RE_0_AFTER_DIGIT.replace_all(&result, "${1}0$3").to_string();
    result = RE_0_BEFORE_DIGIT.replace_all(&result, "0$2").to_string();
    result = RE_0_BETWEEN_DIGITS
        .replace_all(&result, "${1}0$3")
        .to_string();

    // 4-like: A
    result = RE_4_BEFORE_UNIT.replace_all(&result, "4$2").to_string();
    result = RE_4_AFTER_DIGIT.replace_all(&result, "${1}4$3").to_string();

    // 5-like: S
    result = RE_5_BEFORE_UNIT.replace_all(&result, "5$2").to_string();
    result = RE_5_AFTER_DIGIT.replace_all(&result, "${1}5$3").to_string();
    result = RE_5_BEFORE_DIGIT.replace_all(&result, "5$2").to_string();

    // 6-like: G, b
    result = RE_6_BEFORE_UNIT.replace_all(&result, "6$2").to_string();
    result = RE_6_AFTER_DIGIT.replace_all(&result, "${1}6$3").to_string();

    // 8-like: B
    result = RE_8_BEFORE_UNIT.replace_all(&result, "8$2").to_string();
    result = RE_8_AFTER_DIGIT.replace_all(&result, "${1}8$3").to_string();

    // 9-like: g, q
    result = RE_9_BEFORE_UNIT.replace_all(&result, "9$2").to_string();
    result = RE_9_AFTER_DIGIT.replace_all(&result, "${1}9$3").to_string();

    // 2-like: Z
    result = RE_2_BEFORE_UNIT.replace_all(&result, "2$2").to_string();
    result = RE_2_AFTER_DIGIT.replace_all(&result, "${1}2$3").to_string();

    // 7-like: T
    result = RE_7_BEFORE_UNIT.replace_all(&result, "7$2").to_string();
    result = RE_7_AFTER_DIGIT.replace_all(&result, "${1}7$3").to_string();

    result
}

/// Extract a time duration value from text using regex patterns.
///
/// Port of Python `_extract_time_from_text()`.
pub fn extract_time_from_text(text: &str) -> String {
    // First normalize OCR errors
    let text = normalize_ocr_digits(text);

    // Try patterns in priority order

    // "Xh Ym"
    if let Some(caps) = RE_HOUR_MIN.captures(&text) {
        let h: u32 = caps[1].parse().unwrap_or(0);
        let m: u32 = caps[2].parse().unwrap_or(0);
        return format!("{h}h {m}m");
    }

    // "Xh Y" (missing m) — only match when NOT followed by h/m/s unit
    if let Some(caps) = RE_HOUR_MIN_NO_M.captures(&text) {
        // Group 3 captures an optional trailing unit. If absent, this is "Xh Y" without "m".
        if caps.get(3).is_none() {
            let h: u32 = caps[1].parse().unwrap_or(0);
            let m: u32 = caps[2].parse().unwrap_or(0);
            return format!("{h}h {m}m");
        }
    }

    // "Xm Ys"
    if let Some(caps) = RE_MIN_SEC.captures(&text) {
        let m: u32 = caps[1].parse().unwrap_or(0);
        let s_str = caps[2].replace('O', "0");
        let s: u32 = s_str.parse().unwrap_or(0);
        return format!("{m}m {s}s");
    }

    // "Xh"
    if let Some(caps) = RE_HOURS_ONLY.captures(&text) {
        let h: u32 = caps[1].parse().unwrap_or(0);
        return format!("{h}h");
    }

    // "Xm"
    if let Some(caps) = RE_MIN_ONLY.captures(&text) {
        let m: u32 = caps[1].parse().unwrap_or(0);
        return format!("{m}m");
    }

    // "Xs"
    if let Some(caps) = RE_SEC_ONLY.captures(&text) {
        let s_str = caps[1].replace('O', "0");
        let s: u32 = s_str.parse().unwrap_or(0);
        return format!("{s}s");
    }

    String::new()
}

/// Check if text contains any time pattern.
pub fn has_time_pattern(text: &str) -> bool {
    RE_HAS_TIME.is_match(text)
}

// ---------------------------------------------------------------------------
// Daily total page detection
// ---------------------------------------------------------------------------

/// Words indicating a daily total page (not app-specific).
const DAILY_PAGE_MARKERS: &[&str] = &[
    "WEEK",
    "DAY",
    "MOST",
    "USED",
    "CATEGORIES",
    "TODAY",
    "SHOW",
    "ENTERTAINMENT",
    "EDUCATION",
    "INFORMATION",
    "READING",
];

/// Words indicating an app-specific page.
const APP_PAGE_MARKERS: &[&str] = &[
    "INFO",
    "DEVELOPER",
    "RATING",
    "LIMIT",
    "AGE",
    "DAILY",
    "AVERAGE",
];

/// Determine if OCR text indicates a daily total page (vs app-specific).
///
/// Port of Python `is_daily_total_page()`.
pub fn is_daily_total_page(texts: &[String]) -> bool {
    let mut daily_count = 0;
    let mut app_count = 0;

    for text in texts {
        let upper = text.to_uppercase();

        for marker in DAILY_PAGE_MARKERS {
            if upper.contains(marker) {
                daily_count += 1;
                break;
            }
        }

        for marker in APP_PAGE_MARKERS {
            if upper.contains(marker) {
                app_count += 1;
                break;
            }
        }
    }

    daily_count > app_count
}

// ---------------------------------------------------------------------------
// OCR-based title and total extraction (requires leptess)
// ---------------------------------------------------------------------------

use image::RgbImage;
use log::{debug, info};

#[cfg(feature = "ocr")]
use crate::image_utils::adjust_contrast_brightness;
use crate::types::ProcessingError;

/// OCR bounding box from Tesseract (word-level).
/// Shared between ocr.rs and ocr_anchored.rs.
pub struct OcrWord {
    pub text: String,
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}

/// PHI-detection OCR word — like `OcrWord` but carries Tesseract's
/// per-word confidence (0–100).
pub struct PhiWord {
    pub text: String,
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
    pub conf: i32,
}

/// Run Tesseract on an image and return word-level results.
///
/// Uses `set_image_from_mem` to avoid temp file I/O entirely.
#[cfg(feature = "ocr")]
pub fn run_tesseract(img: &RgbImage, psm: &str) -> Result<Vec<OcrWord>, ProcessingError> {
    // Encode the image as BMP, not PNG. The Leptonica WASM build is
    // configured with -DENABLE_PNG=OFF / -DENABLE_ZLIB=OFF (and the
    // Emscripten-port libpng/zlib aren't linked in), so leptess'
    // pixReadMem refuses to decode PNG bytes with
    // 'pixReadMemPng: function not present' and OCR silently returns
    // 'Set image from mem failed: Failed to read image from memory'
    // — which is exactly the symptom in production.
    //
    // BMP is supported by Leptonica's built-in readers without any
    // external library dependency, so it works regardless of how
    // Leptonica was configured. The few extra bytes vs PNG are
    // irrelevant — this is an in-memory transfer, not a network upload.
    let mut bmp_buf = Vec::new();
    let encoder = image::codecs::bmp::BmpEncoder::new(&mut bmp_buf);
    img.write_with_encoder(encoder)
        .map_err(|e| ProcessingError::Ocr(format!("BMP encode failed: {e}")))?;

    with_leptess(psm, |lt| {
        // Match the Python reference, which uses pytesseract's default
        // (no character whitelist). Any whitelist drops characters that
        // legitimately appear in app names — apostrophes, ampersands,
        // accented letters, parentheses, slashes, etc. — and silently
        // blanks the title. Tesseract's eng.traineddata is constrained
        // enough on its own without a hand-curated allow-list.
        lt.set_variable(leptess::Variable::TesseditCharWhitelist, "")
            .ok();
        lt.set_image_from_mem(&bmp_buf)
            .map_err(|e| ProcessingError::Ocr(format!("Set image from mem failed: {e}")))?;
        lt.recognize();
        parse_tsv_words(lt)
    })
}

/// Parse TSV output from a recognized LepTess instance into word-level boxes.
#[cfg(feature = "ocr")]
pub fn parse_tsv_words(lt: &mut leptess::LepTess) -> Result<Vec<OcrWord>, ProcessingError> {
    let tsv = lt.get_tsv_text(0).unwrap_or_default();
    let mut words = Vec::new();

    for line in tsv.lines().skip(1) {
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() >= 12 {
            let text = parts[11].trim().to_string();
            if text.is_empty() {
                continue;
            }
            words.push(OcrWord {
                text,
                x: parts[6].parse().unwrap_or(0),
                y: parts[7].parse().unwrap_or(0),
                w: parts[8].parse().unwrap_or(0),
                h: parts[9].parse().unwrap_or(0),
            });
        }
    }

    Ok(words)
}

/// Run full-page Tesseract OCR for PHI detection — returns every word with
/// bbox + confidence, no character whitelist.
///
/// Used by the WASM PHI pipeline to replace Tesseract.js. The thread-local
/// LepTess instance is shared with `run_tesseract`; this function explicitly
/// clears the digit whitelist so subsequent digit-only calls must re-set it
/// (which `run_tesseract` already does).
#[cfg(feature = "ocr")]
pub fn run_phi_ocr_words(img: &RgbImage) -> Result<Vec<PhiWord>, ProcessingError> {
    // Encode as BMP for the same reason as run_tesseract: the WASM
    // Leptonica build has PNG support disabled, so PNG bytes can't be
    // decoded by pixReadMem. BMP is built into Leptonica.
    let mut bmp_buf = Vec::new();
    let encoder = image::codecs::bmp::BmpEncoder::new(&mut bmp_buf);
    img.write_with_encoder(encoder)
        .map_err(|e| ProcessingError::Ocr(format!("BMP encode failed: {e}")))?;

    with_leptess("3", |lt| {
        // Clear any whitelist a previous digit-only call left behind.
        lt.set_variable(leptess::Variable::TesseditCharWhitelist, "")
            .ok();
        lt.set_image_from_mem(&bmp_buf)
            .map_err(|e| ProcessingError::Ocr(format!("Set image from mem failed: {e}")))?;
        lt.recognize();
        let tsv = lt.get_tsv_text(0).unwrap_or_default();

        let mut words = Vec::new();
        for line in tsv.lines().skip(1) {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() < 12 {
                continue;
            }
            let text = parts[11].trim().to_string();
            if text.is_empty() {
                continue;
            }
            words.push(PhiWord {
                text,
                x: parts[6].parse().unwrap_or(0),
                y: parts[7].parse().unwrap_or(0),
                w: parts[8].parse().unwrap_or(0),
                h: parts[9].parse().unwrap_or(0),
                conf: parts[10].parse().unwrap_or(0),
            });
        }
        Ok(words)
    })
}

/// Sort OCR words in reading order (left-to-right, top-to-bottom).
///
/// Words within `y_tolerance` pixels of each other are considered on the same
/// line and sorted by x only. This prevents 1-2px y jitter from reordering
/// "1h" and "9m" into "9m 1h" when they're visually on the same line.
fn sort_words_reading_order(words: &mut [&OcrWord]) {
    const Y_TOLERANCE: i32 = 8;
    words.sort_by(|a, b| {
        let y_diff = (a.y - b.y).abs();
        if y_diff <= Y_TOLERANCE {
            a.x.cmp(&b.x)
        } else {
            a.y.cmp(&b.y).then(a.x.cmp(&b.x))
        }
    });
}

/// Join OCR words into a single normalized string.
///
/// Applies common OCR cleanup (Os→0s, pipe removal), joins with spaces,
/// and normalizes digit confusions.
fn words_to_normalized_text<'a>(words: impl Iterator<Item = &'a OcrWord>) -> String {
    let raw: String = words
        .map(|w| w.text.replace("Os", "0s").replace('|', ""))
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    normalize_ocr_digits(raw.trim())
}

/// Join OCR words into a title string.
/// Only removes OCR artifacts (pipe chars, non-alphabetic garbage).
/// No title corrections or noise word filtering — that belongs in postprocessing.
fn words_to_title_text<'a>(words: impl Iterator<Item = &'a OcrWord>) -> String {
    let raw: String = words
        .map(|w| w.text.replace('|', ""))
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    // Strip outer artifacts. Tesseract often misreads the small app icon
    // sitting to the left of the title as `~`, `*`, `#`, `_`, etc.,
    // which trickles through as a leading garbage glyph; strip these
    // along with whitespace so the title reads cleanly.
    raw.trim()
        .trim_matches(|c: char| {
            c == '#' || c == '_' || c == '~' || c == '*' || c == '`' || c.is_whitespace()
        })
        .to_string()
}

/// Extract the screenshot title using pre-computed full-image OCR data.
///
/// Tries spatial filtering of full-image OCR words first (no extra Tesseract call).
/// Falls back to crop+re-OCR only when the spatial pass yields nothing.
fn extract_title(
    img: &RgbImage,
    ocr_data: &[OcrWord],
) -> Result<(String, Option<i32>), ProcessingError> {
    // Check if daily total page
    let texts: Vec<String> = ocr_data.iter().map(|w| w.text.clone()).collect();
    if is_daily_total_page(&texts) {
        return Ok(("Daily Total".to_string(), None));
    }

    // Find LAST "INFO" text position — bottom-most match is more likely
    // to be the actual button, not random text. Matches Python's behavior.
    let info_word = ocr_data.iter().rev().find(|w| w.text.contains("INFO"));

    if let Some(info) = info_word {
        let (img_w, _img_h) = img.dimensions();
        let title_y_start = info.y + info.h;
        let title_x_start = (info.x as f64 + 1.5 * info.w as f64) as i32;
        // Match canvas: xWidth = xOrigin + infoWidth * 12, limited to image boundary
        let title_x_end = (title_x_start + info.w * 12).min(img_w as i32);
        // Match the Python reference: app_height = info.h * 7. The
        // previous value (info.h * 4) was a Rust-only deviation that
        // cropped the title row entirely on Pro Max-class displays where
        // the app-name baseline sits roughly six INFO-heights below INFO.
        // The deleted TS canvas port followed the Rust value instead of
        // source-of-truth Python, which is why both ports were silently
        // blanking titles.
        let title_y_end = title_y_start + info.h * 7;

        // Canvas always crops the title region + applies 2× contrast + re-OCRs.
        // No spatial fast path — canvas never reuses full-image OCR words for title.
        // Under no-ocr (WASM JS path): fall back to spatial word filtering since
        // JS handles re-OCR externally via findScreenshotTitle().
        #[cfg(not(feature = "ocr"))]
        {
            let mut title_words: Vec<&OcrWord> = ocr_data
                .iter()
                .filter(|w| {
                    !w.text.is_empty()
                        && w.x >= title_x_start
                        && w.x < title_x_end
                        && w.y >= title_y_start
                        && w.y < title_y_end
                        && !w.text.contains("INFO")
                })
                .collect();
            sort_words_reading_order(&mut title_words);
            let title = words_to_title_text(title_words.iter().copied());
            if !title.is_empty() && title.len() <= 50 {
                return Ok((title, Some(title_y_end)));
            }
        }

        #[cfg(feature = "ocr")]
        {
            let (img_w, img_h) = img.dimensions();
            let x_origin = title_x_start.max(0) as u32;
            let x_end = (title_x_end as u32).min(img_w);
            let y_start = title_y_start.max(0) as u32;
            let y_end = (title_y_end as u32).min(img_h);

            if x_end > x_origin && y_end > y_start {
                let region = image::imageops::crop_imm(
                    img,
                    x_origin,
                    y_start,
                    x_end - x_origin,
                    y_end - y_start,
                )
                .to_image();
                let region_enhanced = adjust_contrast_brightness(&region, 2.0, 0);
                // Python reference uses PSM 3 (auto layout) for the title
                // re-OCR; Rust used to use PSM 6 (single uniform block),
                // which expects multi-line layout and fails on the
                // single-line title crops produced by tall iPhones. Match
                // Python.
                let words = run_tesseract(&region_enhanced, "3")?;

                let title = words_to_title_text(words.iter());

                if title.len() > 50 {
                    info!("Title too long ({} chars), likely OCR garbage", title.len());
                    return Ok((String::new(), Some(y_end as i32)));
                }

                info!("Found title via crop OCR: '{}' at y={}", title, y_end);
                return Ok((title, Some(y_end as i32)));
            }
        }
    }

    // Fallback: no "INFO" found — match the Python reference exactly.
    // Python uses `info_rect = [40, 300, 120, 2000]` then numpy-slices
    // `img[info_rect[0]:info_rect[2], info_rect[1]:info_rect[3]]`, which
    // is `img[y=40:120, x=300:2000]` — an 80-px-tall horizontal strip
    // starting at x=300, clamped to the image width. Both Rust and the
    // deleted TS port had previously invented their own constants here
    // (40..200 × 120..0.55w) which doesn't match source-of-truth.
    #[cfg(feature = "ocr")]
    {
        let (img_w, img_h) = img.dimensions();
        let fb_y_start = 40u32.min(img_h);
        let fb_y_end = 120u32.min(img_h);
        let fb_x_start = 300u32.min(img_w);
        let fb_x_end = 2000u32.min(img_w);

        if fb_x_end > fb_x_start && fb_y_end > fb_y_start {
            let region = image::imageops::crop_imm(
                img,
                fb_x_start,
                fb_y_start,
                fb_x_end - fb_x_start,
                fb_y_end - fb_y_start,
            )
            .to_image();
            let region_enhanced = adjust_contrast_brightness(&region, 2.0, 0);
            let words = run_tesseract(&region_enhanced, "3")?;

            let title = words_to_title_text(words.iter());
            if !title.is_empty() && title.len() <= 50 {
                info!("Found title via fallback region: '{}'", title);
                return Ok((title, Some(fb_y_end as i32)));
            }
        }
    }

    debug!("No title found after all extraction strategies (spatial, crop, hardcoded region)");
    Ok((String::new(), None))
}

/// Extract total screen time using pre-computed full-image OCR data.
///
/// Extracts from spatially-filtered full-image OCR words — no extra Tesseract call.
fn extract_total(img: &RgbImage, ocr_data: &[OcrWord]) -> Result<String, ProcessingError> {
    let texts: Vec<String> = ocr_data.iter().map(|w| w.text.clone()).collect();
    let is_daily = is_daily_total_page(&texts);

    // Find LAST "SCREEN" word — matches Python's behavior of taking last match
    let screen_word = ocr_data.iter().rev().find(|w| w.text.contains("SCREEN"));

    let (img_w, img_h) = img.dimensions();

    if let Some(screen) = screen_word {
        // Compute the same bounding box that the crop+re-OCR path used
        let (x_start, y_start, x_end_approx, y_end_approx) = if is_daily {
            let y = screen.y + screen.h + 95;
            let h = screen.h * 5;
            let x = (screen.x - 50).max(0);
            let w = screen.w * 4;
            (x, y, x + w, y + h)
        } else {
            let h = screen.h * 6;
            let y = screen.y + screen.h + 50;
            let x = (screen.x - 20).max(0);
            // Clamp width to img_width / 3 for app pages to avoid picking up
            // unrelated text on the right side of the screen
            let w = (screen.w * 3).min(img_w as i32 / 3);
            (x, y, x + w, y + h)
        };

        // Collect words in the total region from the full-image OCR data
        let mut region_words: Vec<&OcrWord> = ocr_data
            .iter()
            .filter(|w| {
                !w.text.is_empty()
                    && w.x >= x_start
                    && w.x < x_end_approx
                    && w.y >= y_start
                    && w.y < y_end_approx
            })
            .collect();
        sort_words_reading_order(&mut region_words);

        let total_text = words_to_normalized_text(region_words.iter().copied());
        let extracted = extract_time_from_text(&total_text);
        if !extracted.is_empty() {
            info!(
                "Found total from full-image OCR: '{}' (from '{}')",
                extracted, total_text
            );
            return Ok(extracted);
        }
    }

    // Fallback: when "SCREEN" not found, use hardcoded regions matching Python
    let (fb_y_start, fb_y_end) = if is_daily { (325, 425) } else { (250, 350) };

    let mut region_words: Vec<&OcrWord> = ocr_data
        .iter()
        .filter(|w| {
            !w.text.is_empty() && w.y >= fb_y_start && w.y < fb_y_end && w.x < (img_w as i32 / 3)
        })
        .collect();
    sort_words_reading_order(&mut region_words);

    let fb_text = words_to_normalized_text(region_words.iter().copied());
    let extracted = extract_time_from_text(&fb_text);
    if !extracted.is_empty() {
        info!(
            "Found total via hardcoded region fallback: '{}' (from '{}')",
            extracted, fb_text
        );
        return Ok(extracted);
    }

    // Progressive search: left 1/3 → left 1/2 → full width.
    // Canvas uses 3 tiers: left-third (avoids "Daily Average"), left-half, full image.
    // "Daily Average" at y~674 must be excluded. Use SCREEN word position
    // if available, otherwise cap at img_h/4.
    let y_limit = screen_word
        .map(|sw| sw.y + sw.h + 200) // ~200px below SCREEN word
        .unwrap_or((img_h as i32) / 4);
    for fraction in &[3, 2, 1] {
        let x_limit = img_w as i32 / fraction;
        let prog_text = words_to_normalized_text(
            ocr_data
                .iter()
                .filter(|w| !w.text.is_empty() && w.x < x_limit && w.y < y_limit),
        );
        let total = extract_time_from_text(&prog_text);
        if !total.is_empty() {
            info!(
                "Found total via progressive search (1/{}): '{}'",
                fraction, total
            );
            return Ok(total);
        }
    }

    Ok(String::new())
}

/// Extract both title and total from an image with a SINGLE Tesseract call.
///
/// Runs Tesseract once on the full image, then uses spatial filtering of the
/// resulting word list to extract title and total — no extra Tesseract calls.
/// Daily total pages are detected from the full-image word list; cropping the
/// image would cause markers like "MOST USED" and "CATEGORIES" (which appear
/// in the lower half of daily total pages) to be missed.
///
/// Errors are propagated, not silently swallowed.
#[cfg(feature = "ocr")]
pub fn find_title_and_total(
    img: &RgbImage,
) -> Result<(String, Option<i32>, String), ProcessingError> {
    // Run Tesseract ONCE on the full image. PSM 3 (auto layout) matches
    // the Python reference (`pytesseract.image_to_data(img, config="--psm 3")`)
    // and is what reliably segments the page into label words like INFO
    // and SCREEN that the spatial filter downstream depends on. PSM 6
    // (single uniform block) treats the whole header as one paragraph and
    // can drop those anchor words on tall displays.
    let ocr_data = run_tesseract(img, "3")?;

    // Extract title and total using the cached OCR data.
    // Pass the full image for the title crop fallback (needs full-res pixels).
    let (title, title_y) = extract_title(img, &ocr_data)?;
    let total = extract_total(img, &ocr_data)?;

    Ok((title, title_y, total))
}

/// Extract title and total from an externally-provided word list (e.g. Tesseract.js).
///
/// Used by the WASM module: the caller provides words from the JS OCR engine,
/// and this function applies Rust's spatial filtering and text normalization.
/// `img_width` and `img_height` must match the source image for correct spatial math.
pub fn extract_from_words(
    words: &[OcrWord],
    img_width: u32,
    img_height: u32,
) -> (String, Option<i32>, String) {
    let stub = image::RgbImage::new(img_width, img_height);
    let texts: Vec<String> = words.iter().map(|w| w.text.clone()).collect();
    let is_daily = is_daily_total_page(&texts);
    let (raw_title, title_y) = extract_title(&stub, words).unwrap_or((String::new(), None));
    let title = if is_daily {
        "Daily Total".to_string()
    } else {
        raw_title
    };
    let total = extract_total(&stub, words).unwrap_or_default();
    (title, title_y, total)
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- normalize_ocr_digits ---

    #[test]
    fn test_normalize_i_to_1() {
        assert_eq!(normalize_ocr_digits("I h"), "1 h");
        assert_eq!(normalize_ocr_digits("3I h"), "31 h");
        assert_eq!(normalize_ocr_digits("I2"), "12");
    }

    #[test]
    fn test_normalize_o_to_0() {
        assert_eq!(normalize_ocr_digits("O h"), "0 h");
        assert_eq!(normalize_ocr_digits("1O h"), "10 h");
        assert_eq!(normalize_ocr_digits("O5"), "05");
        assert_eq!(normalize_ocr_digits("1O2"), "102");
    }

    #[test]
    fn test_normalize_s_to_5() {
        assert_eq!(normalize_ocr_digits("S h"), "5 h");
        assert_eq!(normalize_ocr_digits("3S h"), "35 h");
    }

    #[test]
    fn test_normalize_a_to_4() {
        assert_eq!(normalize_ocr_digits("A h"), "4 h");
        assert_eq!(normalize_ocr_digits("1A h"), "14 h");
    }

    #[test]
    fn test_normalize_preserves_normal_text() {
        assert_eq!(normalize_ocr_digits("hello world"), "hello world");
        assert_eq!(normalize_ocr_digits("3h 45m"), "3h 45m");
    }

    // --- extract_time_from_text ---

    #[test]
    fn test_extract_hour_min() {
        assert_eq!(extract_time_from_text("4h 36m"), "4h 36m");
        assert_eq!(extract_time_from_text("12h 5m"), "12h 5m");
        assert_eq!(
            extract_time_from_text("some text 2h 30m more text"),
            "2h 30m"
        );
    }

    #[test]
    fn test_extract_hour_min_no_m() {
        assert_eq!(extract_time_from_text("4h 36"), "4h 36m");
    }

    #[test]
    fn test_extract_min_sec() {
        assert_eq!(extract_time_from_text("45m 30s"), "45m 30s");
        assert_eq!(extract_time_from_text("5m Os"), "5m 0s");
    }

    #[test]
    fn test_extract_hours_only() {
        assert_eq!(extract_time_from_text("3h"), "3h");
    }

    #[test]
    fn test_extract_min_only() {
        assert_eq!(extract_time_from_text("45m"), "45m");
    }

    #[test]
    fn test_extract_sec_only() {
        assert_eq!(extract_time_from_text("30s"), "30s");
    }

    #[test]
    fn test_extract_no_time() {
        assert_eq!(extract_time_from_text("no time here"), "");
        assert_eq!(extract_time_from_text(""), "");
    }

    #[test]
    fn test_extract_with_ocr_errors() {
        // I should become 1, O should become 0
        assert_eq!(extract_time_from_text("Ih 3Om"), "1h 30m");
    }

    // --- is_daily_total_page ---

    #[test]
    fn test_daily_total_page() {
        let texts: Vec<String> = vec![
            "SCREEN".to_string(),
            "TIME".to_string(),
            "MOST".to_string(),
            "USED".to_string(),
            "TODAY".to_string(),
            "CATEGORIES".to_string(),
        ];
        assert!(is_daily_total_page(&texts));
    }

    #[test]
    fn test_app_usage_page() {
        let texts: Vec<String> = vec![
            "Instagram".to_string(),
            "INFO".to_string(),
            "DEVELOPER".to_string(),
            "RATING".to_string(),
            "LIMIT".to_string(),
        ];
        assert!(!is_daily_total_page(&texts));
    }

    #[test]
    fn test_has_time_pattern() {
        assert!(has_time_pattern("4h 36m"));
        assert!(has_time_pattern("45m"));
        assert!(has_time_pattern("30s"));
        assert!(!has_time_pattern("hello world"));
    }

    // Parity: T before unit → 7 (canvas confuses 7 and T in OCR output)
    #[test]
    fn parity_normalize_t_to_7() {
        assert_eq!(normalize_ocr_digits("T h"), "7 h");
        assert_eq!(normalize_ocr_digits("3T h"), "37 h");
    }

    // Parity: G and b before unit → 6 (canvas OCR confusion)
    #[test]
    fn parity_normalize_g_b_to_6() {
        assert_eq!(normalize_ocr_digits("G h"), "6 h");
        assert_eq!(normalize_ocr_digits("b h"), "6 h");
        assert_eq!(normalize_ocr_digits("3G m"), "36 m");
    }

    // Parity: B before unit → 8
    #[test]
    fn parity_normalize_b_to_8() {
        assert_eq!(normalize_ocr_digits("B h"), "8 h");
        assert_eq!(normalize_ocr_digits("3B m"), "38 m");
    }

    // Parity: S before digit → 5 (RE_5_BEFORE_DIGIT covers digit-after-S context)
    #[test]
    fn parity_normalize_s_before_digit() {
        assert_eq!(normalize_ocr_digits("S5"), "55");
        assert_eq!(normalize_ocr_digits("S3"), "53");
    }

    // Parity: 's' unit itself must NOT be corrupted — only capital S before h/m is normalized.
    // Canvas RE_5_BEFORE_UNIT only covers [hm], not 's'. "30s" has no capital S → unchanged.
    #[test]
    fn parity_normalize_s_unit_unchanged() {
        assert_eq!(normalize_ocr_digits("30s"), "30s");
        assert_eq!(normalize_ocr_digits("5m 30s"), "5m 30s");
    }

    // Parity: g, q before unit → 9
    #[test]
    fn parity_normalize_g_q_to_9() {
        assert_eq!(normalize_ocr_digits("g h"), "9 h");
        assert_eq!(normalize_ocr_digits("q m"), "9 m");
        assert_eq!(normalize_ocr_digits("1g h"), "19 h");
    }

    // Parity: Z before unit → 2
    #[test]
    fn parity_normalize_z_to_2() {
        assert_eq!(normalize_ocr_digits("Z h"), "2 h");
        assert_eq!(normalize_ocr_digits("3Z m"), "32 m");
    }

    // Parity: "Xh Y h" and "Xh Y s" must fall through RE_HOUR_MIN_NO_M (group 3 present)
    // and match RE_HOURS_ONLY → return "Xh".
    // Canvas: same pattern — trailing unit after digit means it's not a bare minute count.
    #[test]
    fn parity_extract_time_rejects_ambiguous_hour_digit_with_unit() {
        assert_eq!(
            extract_time_from_text("4h 36 h"),
            "4h",
            "'4h 36 h' — trailing 'h' makes group3 present → skip Xh Y path → hours only"
        );
        assert_eq!(
            extract_time_from_text("4h 36 s"),
            "4h",
            "'4h 36 s' — trailing 's' makes group3 present → skip Xh Y path → hours only"
        );
    }

    // Parity: "Xm Os" — 'O' in seconds position normalized to '0'.
    // Canvas: replaces 'O' with '0'; parses as integer → no leading-zero padding.
    #[test]
    fn parity_extract_time_min_sec_o_as_zero() {
        assert_eq!(extract_time_from_text("5m Os"), "5m 0s");
        // "12m O5s" → normalize O→0 → "12m 05s" → parse 05 as u32=5 → "12m 5s"
        assert_eq!(extract_time_from_text("12m O5s"), "12m 5s");
    }

    // Parity: is_daily_total_page uses daily_count > app_count (strictly greater).
    // A tie (equal counts) → false.
    #[test]
    fn parity_is_daily_total_page_tie_returns_false() {
        let texts: Vec<String> = vec![
            "TODAY".to_string(), // daily marker
            "DAILY".to_string(), // app marker
        ];
        assert!(
            !is_daily_total_page(&texts),
            "tied daily vs app count must return false"
        );
    }

    // Parity: is_daily_total_page ignores case (uses to_uppercase internally).
    #[test]
    fn parity_is_daily_total_page_case_insensitive() {
        let texts: Vec<String> = vec!["Most".to_string(), "Used".to_string(), "today".to_string()];
        assert!(
            is_daily_total_page(&texts),
            "lowercase markers must still match via to_uppercase"
        );
    }
}
