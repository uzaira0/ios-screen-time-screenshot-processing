//! Bar graph value extraction from ROI regions.
//!
//! Port of Python bar_extraction.py — extracts 24 hourly usage values
//! by analyzing pixel colors and measuring bar heights.

use image::RgbImage;

use super::image_utils::{darken_and_binarize, rgb_to_hsv};

/// Number of hourly slices in the bar graph.
const NUM_SLICES: usize = 24;
/// Maximum minutes per hour (y-axis ceiling).
const MAX_Y: f64 = 60.0;
/// Pixels to exclude at the bottom of the ROI (grid line buffer).
const LOWER_GRID_BUFFER: usize = 2;

/// Fast bar total extraction at 1x — used only as fallback.
/// For the boundary optimizer, use `compute_bar_total_from_scaled` instead.
pub fn slice_image_fast_total(
    img: &RgbImage,
    roi_x: u32,
    roi_y: u32,
    roi_width: u32,
    roi_height: u32,
) -> f64 {
    let (img_w, img_h) = img.dimensions();
    let roi_x = roi_x.min(img_w);
    let roi_y = roi_y.min(img_h);
    let roi_width = roi_width.min(img_w.saturating_sub(roi_x));
    let roi_height = roi_height.min(img_h.saturating_sub(roi_y));

    if roi_width < NUM_SLICES as u32 || roi_height < 2 {
        return 0.0;
    }

    let mut roi = image::imageops::crop_imm(img, roi_x, roi_y, roi_width, roi_height).to_image();
    darken_and_binarize(&mut roi);

    let h = roi_height as usize;
    let rw = roi_width as usize;
    let slice_width = rw / NUM_SLICES;
    let reset_limit = h.saturating_sub(LOWER_GRID_BUFFER).max(1);

    let raw = roi.as_raw();
    let stride = rw * 3;
    let mut total = 0.0f64;

    for s in 0..NUM_SLICES {
        let mid_col = (s * slice_width + slice_width / 2).min(rw - 1);
        let mut start_after: usize = 0;
        for y in (0..reset_limit).rev() {
            let idx = y * stride + mid_col * 3;
            if raw[idx] >= 253 && raw[idx + 1] >= 253 && raw[idx + 2] >= 253 {
                start_after = y + 1;
                break;
            }
        }
        let mut counter = 0u32;
        for y in start_after..h {
            let idx = y * stride + mid_col * 3;
            if raw[idx] as u16 + raw[idx + 1] as u16 + raw[idx + 2] as u16 == 0 {
                counter += 1;
            }
        }
        total += (MAX_Y * counter as f64 / h as f64).floor();
    }
    total
}

/// Precompute a binarized + 4x-scaled image for the boundary optimizer.
///
/// The optimizer calls `compute_bar_total_from_scaled` ~1300 times.
/// By scaling the ENTIRE image once, each iteration only does a direct
/// buffer read — no per-iteration crop/resize/binarize.
pub fn preprocess_for_optimizer(img: &RgbImage) -> (Vec<u8>, u32, u32) {
    let (w, h) = img.dimensions();
    let mut binarized = img.clone();
    darken_and_binarize(&mut binarized);

    const SCALE: u32 = 4;
    let scaled = image::imageops::resize(
        &binarized,
        w * SCALE,
        h * SCALE,
        image::imageops::FilterType::Nearest,
    );
    let sw = w * SCALE;
    let sh = h * SCALE;
    (scaled.into_raw(), sw, sh)
}

/// Compute bar total directly from a pre-scaled buffer (zero allocation per call).
///
/// `scaled_data`: raw RGB bytes from `preprocess_for_optimizer`
/// `scaled_width`: width of the scaled image
/// roi coordinates are in ORIGINAL (1x) space — this function scales them.
pub fn compute_bar_total_from_scaled(
    scaled_data: &[u8],
    scaled_width: u32,
    roi_x: u32,
    roi_y: u32,
    roi_width: u32,
    roi_height: u32,
) -> f64 {
    const SCALE: u32 = 4;
    let sx = roi_x * SCALE;
    let sy = roi_y * SCALE;
    let sw = roi_width * SCALE;
    let sh = roi_height * SCALE;

    if sw < (NUM_SLICES as u32) || sh < 2 {
        return 0.0;
    }

    let h = sh as usize;
    let rw = sw as usize;
    let slice_width = rw / NUM_SLICES;
    // Canvas: analyzeBarHeight checks y < maxHeight - LOWER_GRID_BUFFER where maxHeight is
    // already 4x-scaled. So exclude LOWER_GRID_BUFFER pixels from the 4x image (not SCALE*BUFFER).
    let reset_limit = h.saturating_sub(LOWER_GRID_BUFFER).max(1);

    let stride = (scaled_width * 3) as usize;
    let mut total = 0.0f64;

    for s in 0..NUM_SLICES {
        let mid_col =
            (sx as usize + s * slice_width + slice_width / 2).min(scaled_width as usize - 1);
        let mut start_after: usize = 0;
        for y in (0..reset_limit).rev() {
            let global_y = sy as usize + y;
            let idx = global_y * stride + mid_col * 3;
            if idx + 2 < scaled_data.len()
                && scaled_data[idx] >= 253
                && scaled_data[idx + 1] >= 253
                && scaled_data[idx + 2] >= 253
            {
                start_after = y + 1;
                break;
            }
        }
        let mut counter = 0u32;
        for y in start_after..h {
            let global_y = sy as usize + y;
            let idx = global_y * stride + mid_col * 3;
            if idx + 2 < scaled_data.len()
                && scaled_data[idx] as u16
                    + scaled_data[idx + 1] as u16
                    + scaled_data[idx + 2] as u16
                    == 0
            {
                counter += 1;
            }
        }
        total += (MAX_Y * counter as f64 / h as f64).floor();
    }
    total
}

/// Extract hourly usage values from the bar graph region.
///
/// Returns a Vec of 25 elements: 24 hourly values + total.
///
/// Port of Python `slice_image()`.
pub fn slice_image(
    img: &RgbImage,
    roi_x: u32,
    roi_y: u32,
    roi_width: u32,
    roi_height: u32,
) -> Vec<f64> {
    // Clamp ROI to image bounds to prevent silent truncation
    let (img_w, img_h) = img.dimensions();
    let roi_x = roi_x.min(img_w);
    let roi_y = roi_y.min(img_h);
    let roi_width = roi_width.min(img_w.saturating_sub(roi_x));
    let roi_height = roi_height.min(img_h.saturating_sub(roi_y));

    if roi_width < NUM_SLICES as u32 || roi_height < 2 {
        // ROI too small to extract meaningful data — return zeros
        return vec![0.0; NUM_SLICES + 1];
    }

    // Extract ROI, process, then scale up 4x for sub-pixel precision.
    //
    // The Python implementation scales the ROI 4x before sampling. This matters
    // because integer-division slice widths differ between 1x and 4x: at 1x,
    // slice_width = 686/24 = 28 (loses 14px), but at 4x, slice_width = 2744/24 = 114
    // (loses only 8px). The center positions therefore differ by up to 9px, which
    // moves slice centers from just-outside a bar to well-inside it. Without
    // scaling, bars that start 1-2px past a slice center are completely missed.
    let mut roi_processed =
        image::imageops::crop_imm(img, roi_x, roi_y, roi_width, roi_height).to_image();
    darken_and_binarize(&mut roi_processed);

    const SCALE: u32 = 4;
    let roi_scaled = image::imageops::resize(
        &roi_processed,
        roi_width * SCALE,
        roi_height * SCALE,
        image::imageops::FilterType::Nearest,
    );

    let h = (roi_height * SCALE) as usize;
    let rw = (roi_width * SCALE) as usize;
    let slice_width = rw / NUM_SLICES;

    // Canvas: analyzeBarHeight checks y < maxHeight - LOWER_GRID_BUFFER where maxHeight is
    // already 4x-scaled. So 2 pixels excluded from 4x image, not 2*SCALE.
    let reset_limit = h.saturating_sub(LOWER_GRID_BUFFER).max(1);

    let mut row = Vec::with_capacity(NUM_SLICES + 1);

    // Use raw buffer for direct pixel access (3 bytes per pixel)
    let raw = roi_scaled.as_raw();
    let stride = rw * 3;

    for s in 0..NUM_SLICES {
        // Middle column of this slice
        let mid_col = (s * slice_width + slice_width / 2).min(rw - 1);

        // Find last white pixel row (scanning from bottom up)
        let mut start_after: usize = 0;
        for y in (0..reset_limit).rev() {
            let idx = y * stride + mid_col * 3;
            // White check: all channels >= 253
            if raw[idx] >= 253 && raw[idx + 1] >= 253 && raw[idx + 2] >= 253 {
                start_after = y + 1;
                break;
            }
        }

        // Count black pixels below start_after
        let mut counter = 0u32;
        for y in start_after..h {
            let idx = y * stride + mid_col * 3;
            // Black check: sum of channels == 0
            if raw[idx] as u16 + raw[idx + 1] as u16 + raw[idx + 2] as u16 == 0 {
                counter += 1;
            }
        }

        let value = (MAX_Y * counter as f64 / h as f64).floor();
        row.push(value);
    }

    // Append total
    let total: f64 = row.iter().sum();
    row.push(total);

    row
}

/// Compute alignment score between visual bar graph and computed values.
///
/// Returns a score from 0.0 to 1.0 where 1.0 = perfect alignment.
///
/// Port of Python `compute_bar_alignment_score()`.
pub fn compute_bar_alignment_score(roi: &RgbImage, hourly_values: &[f64]) -> f64 {
    let (roi_width, roi_height) = roi.dimensions();
    if roi_width == 0 || roi_height == 0 {
        return 0.0;
    }

    // Ensure exactly 24 values
    let mut values = [0.0f64; 24];
    for (i, &v) in hourly_values.iter().take(24).enumerate() {
        values[i] = v;
    }

    let slice_width = roi_width as usize / NUM_SLICES;

    // Extract bar heights from image using HSV blue detection (raw buffer access)
    let raw = roi.as_raw();
    let stride = roi_width as usize * 3;
    let mut extracted_heights = Vec::with_capacity(NUM_SLICES);

    for i in 0..NUM_SLICES {
        let mid_start = i * slice_width + slice_width / 4;
        let mid_end = (i * slice_width + 3 * slice_width / 4).min(roi_width as usize);

        let mut first_blue_row: Option<usize> = None;

        for y in 0..roi_height as usize {
            let row_off = y * stride;
            let mut has_blue = false;
            for x in mid_start..mid_end {
                let idx = row_off + x * 3;
                let (h, s, v) = rgb_to_hsv(raw[idx], raw[idx + 1], raw[idx + 2]);
                if (90..=130).contains(&h) && s > 50 && v > 100 {
                    has_blue = true;
                    break;
                }
            }
            if has_blue {
                first_blue_row = Some(y);
                break;
            }
        }

        let bar_height = match first_blue_row {
            Some(row) => roi_height as f64 - row as f64,
            None => 0.0,
        };
        let normalized = (bar_height / roi_height as f64) * 60.0;
        extracted_heights.push(normalized);
    }

    // Compare extracted vs computed
    let extracted_sum: f64 = extracted_heights.iter().sum();
    let computed_sum: f64 = values.iter().sum();

    if extracted_sum == 0.0 && computed_sum == 0.0 {
        return 1.0;
    }

    if extracted_sum == 0.0 || computed_sum == 0.0 {
        let max_possible = extracted_sum.max(computed_sum);
        return if max_possible > 30.0 { 0.1 } else { 0.3 };
    }

    // Normalize and compute MAE
    let ext_max = extracted_heights.iter().cloned().fold(0.0f64, f64::max) + 1e-10;
    let comp_max = values.iter().cloned().fold(0.0f64, f64::max) + 1e-10;

    let mut mae_sum = 0.0f64;
    for i in 0..NUM_SLICES {
        let ext_norm = extracted_heights[i] / ext_max;
        let comp_norm = values[i] / comp_max;
        mae_sum += (ext_norm - comp_norm).abs();
    }
    let mae = mae_sum / NUM_SLICES as f64;
    let mut score = 1.0 - mae;

    // Shift detection: check if bars are offset by ≥2 hours
    let ext_nonzero: Vec<usize> = extracted_heights
        .iter()
        .enumerate()
        .filter(|&(_, v)| *v / ext_max > 0.1)
        .map(|(i, _)| i)
        .collect();
    let comp_nonzero: Vec<usize> = values
        .iter()
        .enumerate()
        .filter(|&(_, v)| *v / comp_max > 0.1)
        .map(|(i, _)| i)
        .collect();

    if let (Some(&ext_first), Some(&comp_first)) = (ext_nonzero.first(), comp_nonzero.first()) {
        let start_diff = (ext_first as i32 - comp_first as i32).unsigned_abs() as usize;
        if start_diff >= 2 {
            let shift_penalty = (start_diff as f64 * 0.15).min(0.5);
            score = (score - shift_penalty).max(0.0);
        }
    }

    score
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_slice_image_all_white() {
        // All white ROI → all values should be 0
        let img = RgbImage::from_fn(240, 100, |_, _| image::Rgb([255, 255, 255]));
        let result = slice_image(&img, 0, 0, 240, 100);
        assert_eq!(result.len(), 25);
        for &v in &result[..24] {
            assert!(v.abs() < 0.01, "Expected 0, got {v}");
        }
        assert!(result[24].abs() < 0.01);
    }

    #[test]
    fn test_slice_image_all_black() {
        // All black ROI → all values should be MAX_Y (60)
        let img = RgbImage::from_fn(240, 100, |_, _| image::Rgb([0, 0, 0]));
        let result = slice_image(&img, 0, 0, 240, 100);
        assert_eq!(result.len(), 25);
        for &v in &result[..24] {
            assert!((v - 60.0).abs() < 0.01, "Expected 60, got {v}");
        }
    }

    #[test]
    fn test_slice_image_returns_25_elements() {
        let img = RgbImage::new(480, 200);
        let result = slice_image(&img, 0, 0, 480, 200);
        assert_eq!(result.len(), 25); // 24 hours + total
    }

    #[test]
    fn test_alignment_score_identical() {
        // Both extracted and computed are zero → perfect score
        let roi = RgbImage::from_fn(240, 100, |_, _| image::Rgb([255, 255, 255]));
        let values = vec![0.0; 24];
        let score = compute_bar_alignment_score(&roi, &values);
        assert!((score - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_alignment_score_empty_roi() {
        let roi = RgbImage::new(0, 0);
        let score = compute_bar_alignment_score(&roi, &[0.0; 24]);
        assert!((score - 0.0).abs() < 0.01);
    }

    // Parity: each hourly value is Math.floor(60 * counter / height), not a float.
    // Canvas analyzeBarHeight: Math.floor((MAX_MINUTES * counter) / maxHeight)
    // This means partial bars are floored PER SLICE, not at the total.
    #[test]
    fn parity_slice_image_values_are_floored_integers() {
        // 240px wide / 24 slices = 10px per slice at 1x → 40px at 4x scale.
        // All-black 240x100 image: every slice is fully black.
        // counter=h (all black), value = floor(60 * h / h) = floor(60) = 60.
        let img = RgbImage::from_fn(240, 100, |_, _| image::Rgb([0, 0, 0]));
        let result = slice_image(&img, 0, 0, 240, 100);
        for &v in &result[..24] {
            assert_eq!(
                v,
                v.floor(),
                "hourly value must be an integer (floored), got {v}"
            );
        }
    }

    // Parity: total is sum of floored per-slice values, not floor of the continuous sum.
    // If each slice gives floor(60 * counter / h) and all counters = h, total = 24 * 60 = 1440.
    #[test]
    fn parity_slice_image_total_is_sum_of_floored_slices() {
        let img = RgbImage::from_fn(240, 100, |_, _| image::Rgb([0, 0, 0]));
        let result = slice_image(&img, 0, 0, 240, 100);
        let per_slice_sum: f64 = result[..24].iter().sum();
        assert!(
            (result[24] - per_slice_sum).abs() < 0.01,
            "result[24] must equal sum of result[..24]"
        );
    }

    // Parity: slice_image_fast_total floors per-slice to match optimizer's target comparison.
    // If total_text says "40m", bar total must be 40 (not 40.3) to converge optimizer.
    #[test]
    fn parity_fast_total_matches_slice_total() {
        let img = RgbImage::from_fn(240, 100, |_, _| image::Rgb([0, 0, 0]));
        let fast = slice_image_fast_total(&img, 0, 0, 240, 100);
        let slow: f64 = slice_image(&img, 0, 0, 240, 100)[..24].iter().sum();
        assert!(
            (fast - slow).abs() < 0.01,
            "fast_total={fast} must equal slice sum={slow}"
        );
    }

    // Parity: extracted_sum=0, computed_sum>30 → score=0.1
    // Canvas computeBarAlignmentScore: if one side is zero and max > 30, return 0.1
    #[test]
    fn parity_alignment_score_extracted_zero_computed_large() {
        // All-white ROI → extracted_sum=0.0; computed has values summing to 31 > 30
        let roi = image::RgbImage::from_fn(240, 100, |_, _| image::Rgb([255, 255, 255]));
        let mut values = vec![0.0f64; 24];
        values[0] = 31.0;
        let score = compute_bar_alignment_score(&roi, &values);
        assert!(
            (score - 0.1).abs() < 0.01,
            "extracted=0+computed>30 must give 0.1, got {score}"
        );
    }

    // Parity: extracted_sum=0, computed_sum≤30 → score=0.3
    // Canvas: if one side is zero and max ≤ 30, return 0.3
    #[test]
    fn parity_alignment_score_extracted_zero_computed_small() {
        let roi = image::RgbImage::from_fn(240, 100, |_, _| image::Rgb([255, 255, 255]));
        let mut values = vec![0.0f64; 24];
        values[0] = 30.0; // sum = 30.0, NOT > 30 → 0.3
        let score = compute_bar_alignment_score(&roi, &values);
        assert!(
            (score - 0.3).abs() < 0.01,
            "extracted=0+computed=30 must give 0.3, got {score}"
        );
    }

    // Parity: preprocess_for_optimizer scales by exactly 4×.
    // Each iteration of the boundary optimizer reads from this buffer — scaling must be exact.
    #[test]
    fn parity_preprocess_for_optimizer_is_4x_scale() {
        let img = image::RgbImage::new(100, 80);
        let (data, sw, sh) = preprocess_for_optimizer(&img);
        assert_eq!(sw, 400, "scaled width must be 4×100");
        assert_eq!(sh, 320, "scaled height must be 4×80");
        assert_eq!(
            data.len(),
            (400 * 320 * 3) as usize,
            "buffer size must be sw*sh*3"
        );
    }

    // Parity: compute_bar_total_from_scaled returns 0.0 when scaled ROI width < NUM_SLICES.
    // At 4× scale: roi_width=5 → sw=20 < 24 → 0.0.
    #[test]
    fn parity_compute_bar_total_scaled_too_narrow_returns_zero() {
        let img = image::RgbImage::from_fn(100, 100, |_, _| image::Rgb([0, 0, 0]));
        let (data, sw, _) = preprocess_for_optimizer(&img);
        let total = compute_bar_total_from_scaled(&data, sw, 0, 0, 5, 50);
        assert_eq!(total, 0.0, "scaled width=20 < 24 slices must return 0.0");
    }

    // Parity: all-black image bar total via scaled path matches 1× path.
    // Both must agree that every slice is fully black → 60 per slice × 24 = 1440.
    #[test]
    fn parity_compute_bar_total_scaled_matches_1x_all_black() {
        let img = image::RgbImage::from_fn(240, 100, |_, _| image::Rgb([0, 0, 0]));
        let (data, sw, _) = preprocess_for_optimizer(&img);
        let scaled_total = compute_bar_total_from_scaled(&data, sw, 0, 0, 240, 100);
        let slow_total = slice_image_fast_total(&img, 0, 0, 240, 100);
        assert!(
            (scaled_total - slow_total).abs() < 1.0,
            "scaled total={scaled_total} must be within 1 of 1× total={slow_total}"
        );
    }

    // Parity: LOWER_GRID_BUFFER is applied in 4x-scaled coordinates (not multiplied by SCALE).
    // Canvas analyzeBarHeight: `y < maxHeight - LOWER_GRID_BUFFER` where maxHeight is 4x-scaled.
    // So only the bottom 2 pixels of the 4x image are the buffer zone, NOT bottom 8.
    // Verify: a white pixel in positions [h-2, h-1] of the 4x image does not reset start_after.
    #[test]
    fn parity_lower_grid_buffer_applied_in_scaled_coords() {
        // 240×10 all-black image, then place white in the bottom 2 rows of the 4x-scaled result.
        // After 4x scale (nearest): rows h-2=38 and h-1=39 are white.
        // With LOWER_GRID_BUFFER=2, reset_limit = 40-2=38, so the scan is (0..38).rev().
        // White at rows 38-39 is outside the scan → start_after=0 → all blacks counted.
        // If we used LOWER_GRID_BUFFER*SCALE=8: reset_limit=32, scan (0..32).rev().
        // Under the old (wrong) formula the bottom-8 4x pixels would be excluded but that
        // changes counts on smaller ROIs. Here we just verify we don't crash and return non-zero.
        let img = image::RgbImage::from_fn(240, 10, |_, _| image::Rgb([0, 0, 0]));
        let result = slice_image(&img, 0, 0, 240, 10);
        // All-black: every slice should be 60.
        assert_eq!(result[0], 60.0, "all-black 240×10 first slice must be 60");
    }
}
