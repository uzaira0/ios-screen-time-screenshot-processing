//! Boundary optimizer for fine-tuning grid bounds to match OCR totals.
//!
//! Port of Python boundary_optimizer.py — tries small shifts in x, y, and width
//! to find the grid configuration where extracted bar totals best match the
//! OCR-extracted total time string.

use image::RgbImage;
use lazy_static::lazy_static;
use log::{debug, info, warn};
use regex::Regex;

use super::{
    bar_extraction::{
        compute_bar_total_from_scaled, preprocess_for_optimizer, slice_image_fast_total,
    },
    image_utils::remove_all_but,
    ocr::normalize_ocr_digits,
    types::{GridBounds, ImageType},
};

lazy_static! {
    static ref RE_HOURS: Regex = Regex::new(r"(\d{1,2})\s*h").unwrap();
    // Rust regex doesn't support lookahead (?!s). Use \b (word boundary)
    // which rejects "ms" since 's' is a word character following 'm'.
    static ref RE_MINUTES: Regex = Regex::new(r"(\d{1,2})\s*m\b").unwrap();
    static ref RE_SECONDS: Regex = Regex::new(r"(\d{1,2})\s*s").unwrap();
}

/// Result of boundary optimization.
#[derive(Debug, Clone)]
pub struct OptimizationResult {
    pub bounds: GridBounds,
    pub bar_total_minutes: i32,
    pub ocr_total_minutes: i32,
    /// OCR total string after 7→1 digit correction (may differ from the raw OCR input).
    pub corrected_total: String,
    pub shift_x: i32,
    pub shift_y: i32,
    pub shift_width: i32,
    pub iterations: u32,
    pub converged: bool,
}

/// Parse an OCR total string like "1h 31m", "45m", "2h" into total minutes.
/// Returns None if parsing fails.
pub fn parse_ocr_total(ocr_total: &str) -> Option<i32> {
    if ocr_total.is_empty() || ocr_total == "N/A" {
        return None;
    }

    let normalized = normalize_ocr_digits(ocr_total);
    let text = normalized.trim().to_lowercase();

    let mut total_minutes: i32 = 0;

    // Extract hours: digits followed by 'h'
    if let Some(cap) = RE_HOURS.captures(&text) {
        if let Ok(h) = cap[1].parse::<i32>() {
            total_minutes += h * 60;
        }
    }

    // Extract minutes: digits followed by 'm' (not 'ms')
    if let Some(cap) = RE_MINUTES.captures(&text) {
        if let Ok(m) = cap[1].parse::<i32>() {
            total_minutes += m;
        }
    }

    // Seconds-only → rounds to 0 minutes
    if total_minutes == 0 && RE_SECONDS.is_match(&text) {
        return Some(0);
    }

    if total_minutes > 0 {
        Some(total_minutes)
    } else {
        None
    }
}

/// Apply OCR 7→1 correction: if replacing a '7' with '1' brings the parsed
/// total closer to bar_total, use the corrected value.
fn correct_ocr_7_to_1(ocr_total: &str, bar_total_minutes: i32) -> (String, i32) {
    let original_minutes = parse_ocr_total(ocr_total).unwrap_or(0);
    let mut best_total = ocr_total.to_string();
    let mut best_minutes = original_minutes;
    let mut best_diff = (best_minutes - bar_total_minutes).unsigned_abs();

    let chars: Vec<char> = ocr_total.chars().collect();
    let positions: Vec<usize> = chars
        .iter()
        .enumerate()
        .filter(|(_, &c)| c == '7')
        .map(|(i, _)| i)
        .collect();

    // Single replacements
    for &pos in &positions {
        let alt: String = chars
            .iter()
            .enumerate()
            .map(|(i, &c)| if i == pos { '1' } else { c })
            .collect();
        if let Some(mins) = parse_ocr_total(&alt) {
            let diff = (mins - bar_total_minutes).unsigned_abs();
            if diff < best_diff {
                info!(
                    "OCR 7->1 correction: '{}' ({}) -> '{}' ({}) [bar={}]",
                    ocr_total, best_minutes, alt, mins, bar_total_minutes
                );
                best_total = alt;
                best_minutes = mins;
                best_diff = diff;
            }
        }
    }

    // All 7s replaced
    if positions.len() > 1 {
        let alt = ocr_total.replace('7', "1");
        if let Some(mins) = parse_ocr_total(&alt) {
            let diff = (mins - bar_total_minutes).unsigned_abs();
            if diff < best_diff {
                info!(
                    "OCR 7->1 correction (all): '{}' -> '{}' ({}) [bar={}]",
                    ocr_total, alt, mins, bar_total_minutes
                );
                best_total = alt;
                best_minutes = mins;
            }
        }
    }

    (best_total, best_minutes)
}

/// Extract bar total for given bounds from the precomputed 4x-scaled buffer.
/// For battery images, falls back to per-call extraction (battery needs color filtering).
fn extract_bar_total_fast(
    scaled_data: &[u8],
    scaled_width: u32,
    img: &RgbImage,
    bounds: &GridBounds,
    image_type: ImageType,
) -> Option<f64> {
    let (img_w, img_h) = img.dimensions();

    let roi_x = bounds.roi_x();
    let roi_y = bounds.roi_y();
    let roi_w = bounds.width();
    let roi_h = bounds.height();

    if roi_x < 0 || roi_y < 0 || roi_w <= 0 || roi_h <= 0 {
        return None;
    }
    if (roi_x + roi_w) as u32 > img_w || (roi_y + roi_h) as u32 > img_h {
        return None;
    }

    let total = if image_type == ImageType::Battery {
        // Battery needs color filtering — can't use precomputed buffer
        let roi_base =
            image::imageops::crop_imm(img, roi_x as u32, roi_y as u32, roi_w as u32, roi_h as u32)
                .to_image();
        let mut roi = roi_base.clone();
        remove_all_but(&mut roi, [255, 121, 0], 30);
        let t = slice_image_fast_total(&roi, 0, 0, roi_w as u32, roi_h as u32);
        if t == 0.0 {
            let mut roi2 = roi_base;
            remove_all_but(&mut roi2, [0, 134, 255], 30);
            slice_image_fast_total(&roi2, 0, 0, roi_w as u32, roi_h as u32)
        } else {
            t
        }
    } else {
        // Screen time: read directly from precomputed 4x buffer (zero allocation)
        compute_bar_total_from_scaled(
            scaled_data,
            scaled_width,
            roi_x as u32,
            roi_y as u32,
            roi_w as u32,
            roi_h as u32,
        )
    };

    Some(total)
}

/// Optimize grid boundaries to match OCR total.
///
/// Port of Python `optimize_boundaries()`. Tries shifts in x, y, and width
/// to find the configuration where extracted bar totals best match the OCR total.
///
/// - x and width use step=2
/// - y uses step=1 (finer vertical control)
/// - horizontal shifts (x, width) penalized 5× more than vertical (y) in tie-breaks
pub fn optimize_boundaries(
    img: &RgbImage,
    initial_bounds: &GridBounds,
    ocr_total: &str,
    max_shift: i32,
    image_type: ImageType,
) -> OptimizationResult {
    let (img_w, img_h) = img.dimensions();

    let target_minutes = match parse_ocr_total(ocr_total) {
        Some(m) => m,
        None => {
            warn!("Could not parse OCR total: '{}'", ocr_total);
            let bar_total = slice_image_fast_total(
                img,
                initial_bounds.roi_x() as u32,
                initial_bounds.roi_y() as u32,
                initial_bounds.width() as u32,
                initial_bounds.height() as u32,
            ) as i32;
            return OptimizationResult {
                bounds: *initial_bounds,
                bar_total_minutes: bar_total,
                ocr_total_minutes: 0,
                corrected_total: ocr_total.to_string(),
                shift_x: 0,
                shift_y: 0,
                shift_width: 0,
                iterations: 0,
                converged: false,
            };
        }
    };

    // Precompute binarized + 4x-scaled image ONCE for the optimizer loop.
    // This gives 4x precision on every iteration with zero per-iteration allocation.
    let (scaled_data, scaled_width, _scaled_height) = preprocess_for_optimizer(img);

    let mut best_bounds = *initial_bounds;
    let mut best_diff = i32::MAX;
    let mut best_bar_total = 0i32;
    let mut best_shift_x = 0i32;
    let mut best_shift_y = 0i32;
    let mut best_shift_width = 0i32;
    let mut iterations = 0u32;

    // x and width step=2, y step=1
    let mut sx = -max_shift;
    while sx <= max_shift {
        let mut sy = -max_shift;
        while sy <= max_shift {
            let mut sw = -max_shift;
            while sw <= max_shift {
                iterations += 1;

                let new_x = initial_bounds.upper_left_x + sx;
                let new_y = initial_bounds.upper_left_y + sy;
                let new_w = initial_bounds.width() + sw;
                let new_h = initial_bounds.height();

                // Validate
                if new_x < 0 || new_y < 0 || new_w <= 0 {
                    sw += 2;
                    continue;
                }
                if (new_x + new_w) as u32 > img_w || (new_y + new_h) as u32 > img_h {
                    sw += 2;
                    continue;
                }

                let test_bounds = GridBounds::new(new_x, new_y, new_x + new_w, new_y + new_h);

                let bar_total = match extract_bar_total_fast(
                    &scaled_data,
                    scaled_width,
                    img,
                    &test_bounds,
                    image_type,
                ) {
                    Some(t) => t as i32,
                    None => {
                        sw += 2;
                        continue;
                    }
                };

                let diff = (bar_total - target_minutes).abs();
                let shift_penalty = 5 * sx.abs() + sy.abs() + 5 * sw.abs();
                let best_shift_penalty =
                    5 * best_shift_x.abs() + best_shift_y.abs() + 5 * best_shift_width.abs();

                let is_better =
                    diff < best_diff || (diff == best_diff && shift_penalty < best_shift_penalty);

                if is_better {
                    best_diff = diff;
                    best_bounds = test_bounds;
                    best_bar_total = bar_total;
                    best_shift_x = sx;
                    best_shift_y = sy;
                    best_shift_width = sw;

                    // Early exit: exact match with no shift
                    if diff == 0 && shift_penalty == 0 {
                        debug!("Boundary optimizer: exact match at origin");
                        return OptimizationResult {
                            bounds: best_bounds,
                            bar_total_minutes: best_bar_total,
                            ocr_total_minutes: target_minutes,
                            corrected_total: ocr_total.to_string(),
                            shift_x: best_shift_x,
                            shift_y: best_shift_y,
                            shift_width: best_shift_width,
                            iterations,
                            converged: true,
                        };
                    }
                }

                sw += 2;
            }
            sy += 1;
        }
        sx += 2;
    }

    // Apply 7→1 OCR correction using bar total as hint
    let (corrected_str, corrected_minutes) = correct_ocr_7_to_1(ocr_total, best_bar_total);
    let final_diff = (best_bar_total - corrected_minutes).abs();

    debug!(
        "Boundary optimizer: shift=({},{},{}) bar={} ocr={} (orig={}) diff={}",
        best_shift_x,
        best_shift_y,
        best_shift_width,
        best_bar_total,
        corrected_minutes,
        target_minutes,
        final_diff
    );

    OptimizationResult {
        bounds: best_bounds,
        bar_total_minutes: best_bar_total,
        ocr_total_minutes: corrected_minutes,
        corrected_total: corrected_str,
        shift_x: best_shift_x,
        shift_y: best_shift_y,
        shift_width: best_shift_width,
        iterations,
        converged: final_diff <= 1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_ocr_total_hours_and_minutes() {
        assert_eq!(parse_ocr_total("1h 31m"), Some(91));
        assert_eq!(parse_ocr_total("4h 36m"), Some(276));
        assert_eq!(parse_ocr_total("2h"), Some(120));
        assert_eq!(parse_ocr_total("45m"), Some(45));
    }

    #[test]
    fn test_parse_ocr_total_seconds_only() {
        assert_eq!(parse_ocr_total("30s"), Some(0));
    }

    #[test]
    fn test_parse_ocr_total_invalid() {
        assert_eq!(parse_ocr_total(""), None);
        assert_eq!(parse_ocr_total("N/A"), None);
        assert_eq!(parse_ocr_total("no time"), None);
    }

    #[test]
    fn test_parse_ocr_total_normalized() {
        // normalize_ocr_digits converts I→1, O→0
        assert_eq!(parse_ocr_total("Ih 31m"), Some(91));
    }

    // Parity: parse_ocr_total uses \b word boundary for minutes to reject "ms" (milliseconds).
    // Canvas uses a simple character map that also blocks "ms" via unit normalization.
    #[test]
    fn parity_parse_ocr_total_rejects_ms() {
        // "30ms" should not match minutes — 's' after 'm' is a word char, \b rejects it.
        assert_eq!(parse_ocr_total("30ms"), None);
        // "30m" with no following word char must match.
        assert_eq!(parse_ocr_total("30m"), Some(30));
    }

    // Parity: seconds-only returns Some(0) — canvas extractTimeFromText also returns 0 for "Xs".
    #[test]
    fn parity_parse_ocr_total_seconds_returns_zero() {
        assert_eq!(parse_ocr_total("45s"), Some(0));
        assert_eq!(parse_ocr_total("1s"), Some(0));
    }

    // Parity: mixed hours+minutes+seconds — only h and m count, s is ignored.
    #[test]
    fn parity_parse_ocr_total_hms_ignores_seconds() {
        assert_eq!(parse_ocr_total("1h 30m 45s"), Some(90)); // same as 1h 30m
    }

    // Parity: canvas optimizeBoundaries has NO bogus-optimization rejection.
    // When bar_total=0 and ocr_total>0, canvas returns the best-scoring (possibly blank) bounds.
    // Rust must do the same — no early revert to initial_bounds.
    // This test verifies optimize_boundaries runs to completion and returns a result
    // (even if suboptimal) rather than reverting when bar extraction yields 0.
    #[test]
    fn parity_no_bogus_optimization_rejection() {
        // All-white image: bar extraction gives 0 for every candidate. OCR total = "30m".
        let img = image::RgbImage::from_fn(400, 600, |_, _| image::Rgb([255, 255, 255]));
        let bounds = GridBounds::from_roi(10, 100, 380, 400);
        let result = optimize_boundaries(&img, &bounds, "30m", 2, ImageType::ScreenTime);
        // Must complete and return a result (not panic). bar_total may be 0.
        // Canvas: no rejection, just returns whatever the optimizer found.
        let _ = result.bar_total_minutes; // no assertion on value — parity is about not crashing/reverting
    }
}
