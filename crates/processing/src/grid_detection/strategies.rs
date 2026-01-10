//! Line detection strategies — horizontal and vertical grid line analysis.
//!
//! Port of Python strategies/horizontal_lines.py and strategies/vertical_lines.py.
//!
//! Optimized: uses raw RGB buffer indexing instead of get_pixel() and avoids
//! allocating a full grayscale image (computes luma inline).

use image::RgbImage;

/// Gray value range for detecting grid lines.
const GRAY_MIN: u8 = 195;
const GRAY_MAX: u8 = 210;
/// Minimum percentage of row width that must be gray for horizontal line detection.
const MIN_WIDTH_PCT: f64 = 0.35;
/// Gray range for vertical lines (slightly wider).
const V_GRAY_MIN: u8 = 190;
const V_GRAY_MAX: u8 = 215;
/// Minimum percentage of column height for vertical line detection.
const MIN_HEIGHT_PCT: f64 = 0.4;
/// Maximum spacing deviation (pixels) for evenly-spaced lines.
const MAX_SPACING_DEVIATION: i32 = 10;

/// Compute approximate grayscale from RGB (fast integer math, no float).
/// Uses (R + G + B) / 3 which is close enough for grid line detection.
#[inline(always)]
pub fn fast_luma(r: u8, g: u8, b: u8) -> u8 {
    ((r as u16 + g as u16 + b as u16) / 3) as u8
}

/// A group of evenly-spaced horizontal lines.
#[derive(Debug, Clone)]
pub struct LineGroup {
    pub y_start: i32,
    pub y_end: i32,
    pub num_lines: usize,
    pub mean_spacing: f64,
    pub max_deviation: f64,
    pub height_score: f64,
    pub lines: Vec<i32>,
}

/// Find horizontal grid lines in an image region.
///
/// Uses direct buffer access instead of get_pixel() and computes
/// grayscale inline to avoid allocating a separate GrayImage.
pub fn find_horizontal_lines(img: &RgbImage, x_start: u32, x_end: u32) -> Vec<i32> {
    let (w, h) = img.dimensions();
    let region_w = x_end.saturating_sub(x_start);
    if region_w == 0 {
        return Vec::new();
    }

    let raw = img.as_raw();
    let stride = w as usize * 3; // bytes per row
    let threshold = (region_w as f64 * MIN_WIDTH_PCT) as u32;

    let mut line_positions = Vec::new();

    for y in 0..h {
        let row_offset = y as usize * stride;
        let mut gray_count = 0u32;

        for x in x_start..x_end {
            let idx = row_offset + x as usize * 3;
            let luma = fast_luma(raw[idx], raw[idx + 1], raw[idx + 2]);
            if luma >= GRAY_MIN && luma <= GRAY_MAX {
                gray_count += 1;
            }
        }

        if gray_count > threshold {
            line_positions.push(y as i32);
        }
    }

    cluster_positions(&line_positions, 3)
}

/// Find groups of evenly-spaced horizontal lines.
pub fn find_evenly_spaced_groups(lines: &[i32], expected_height: Option<i32>) -> Vec<LineGroup> {
    let min_lines = 4usize;
    let max_lines = 8usize;
    let mut groups = Vec::new();

    for start_idx in 0..lines.len().saturating_sub(min_lines - 1) {
        let end_max = (start_idx + max_lines + 1).min(lines.len() + 1);
        for end_idx in (start_idx + min_lines)..end_max {
            let group = &lines[start_idx..end_idx];
            let spacings: Vec<i32> = group.windows(2).map(|w| w[1] - w[0]).collect();
            let mean_spacing: f64 = spacings.iter().sum::<i32>() as f64 / spacings.len() as f64;
            let max_dev = spacings
                .iter()
                .map(|&s| (s as f64 - mean_spacing).abs())
                .fold(0.0f64, f64::max);

            if max_dev > MAX_SPACING_DEVIATION as f64 {
                continue;
            }
            if mean_spacing < 20.0 || mean_spacing > 150.0 {
                continue;
            }

            let height_score = if let Some(expected) = expected_height {
                let group_height = group.last().unwrap() - group.first().unwrap();
                let error = (group_height - expected).abs() as f64;
                (1.0 - error / expected as f64).max(0.5)
            } else {
                1.0
            };

            groups.push(LineGroup {
                y_start: *group.first().unwrap(),
                y_end: *group.last().unwrap(),
                num_lines: group.len(),
                mean_spacing,
                max_deviation: max_dev,
                height_score,
                lines: group.to_vec(),
            });
        }
    }

    // Sort: most lines DESC, height_score DESC, max_deviation ASC
    // (matches Python: key=lambda g: (-g["num_lines"], -g["height_score"], g["max_deviation"]))
    groups.sort_by(|a, b| {
        b.num_lines
            .cmp(&a.num_lines)
            .then(b.height_score.partial_cmp(&a.height_score).unwrap())
            .then(a.max_deviation.partial_cmp(&b.max_deviation).unwrap())
    });

    // Remove overlapping groups
    let mut non_overlapping = Vec::new();
    for g in &groups {
        let overlaps = non_overlapping.iter().any(|existing: &LineGroup| {
            let start = g.y_start.max(existing.y_start);
            let end = g.y_end.min(existing.y_end);
            end > start
        });
        if !overlaps {
            non_overlapping.push(g.clone());
        }
    }

    non_overlapping
}

/// Count vertical dotted lines in a region and return their x-positions.
///
/// Uses direct buffer access for speed.
pub fn count_vertical_lines(
    img: &RgbImage,
    x_start: u32,
    width: u32,
    y_start: u32,
    y_end: u32,
) -> (usize, Vec<i32>) {
    let (w, _h) = img.dimensions();
    let region_h = y_end.saturating_sub(y_start);
    if region_h == 0 || width == 0 {
        return (0, Vec::new());
    }

    let raw = img.as_raw();
    let stride = w as usize * 3;
    let threshold = (region_h as f64 * MIN_HEIGHT_PCT) as u32;

    let mut positions = Vec::new();

    for x in x_start..(x_start + width).min(w) {
        let mut gray_count = 0u32;
        for y in y_start..y_end.min(img.height()) {
            let idx = y as usize * stride + x as usize * 3;
            let luma = fast_luma(raw[idx], raw[idx + 1], raw[idx + 2]);
            if luma >= V_GRAY_MIN && luma <= V_GRAY_MAX {
                gray_count += 1;
            }
        }
        if gray_count > threshold {
            positions.push(x as i32);
        }
    }

    let clusters = cluster_positions(&positions, 5);
    (clusters.len(), clusters)
}

/// Validate that a region matches daily chart vertical line pattern.
///
/// Returns (is_daily, confidence, v_count, v_positions).
pub fn validate_vertical_lines(
    img: &RgbImage,
    x_start: u32,
    width: u32,
    y_start: u32,
    y_end: u32,
) -> (bool, f64, usize, Vec<i32>) {
    let (v_count, v_positions) = count_vertical_lines(img, x_start, width, y_start, y_end);

    // Expected: 3-5 vertical lines (daily chart)
    if !(3..=5).contains(&v_count) {
        return (false, 0.0, v_count, v_positions);
    }

    if v_positions.len() < 2 {
        return (false, 0.0, v_count, v_positions);
    }

    // Check spacing ≈ width/4
    let spacings: Vec<i32> = v_positions.windows(2).map(|w| w[1] - w[0]).collect();
    let mean_spacing: f64 = spacings.iter().sum::<i32>() as f64 / spacings.len() as f64;
    let expected_spacing = width as f64 / 4.0;

    let spacing_error = (mean_spacing - expected_spacing).abs() / expected_spacing;
    if spacing_error > 0.25 {
        return (false, 0.0, v_count, v_positions);
    }

    // Check consistency
    let max_deviation = spacings
        .iter()
        .map(|&s| (s as f64 - mean_spacing).abs())
        .fold(0.0f64, f64::max);
    if max_deviation > mean_spacing * 0.15 {
        return (false, 0.0, v_count, v_positions);
    }

    let confidence =
        (0.8 + (1.0 - spacing_error) * 0.1 + (1.0 - max_deviation / mean_spacing) * 0.1).min(0.99);

    (true, confidence, v_count, v_positions)
}

/// Cluster nearby integer positions (merge positions within max_gap).
pub fn cluster_positions(positions: &[i32], max_gap: i32) -> Vec<i32> {
    if positions.is_empty() {
        return Vec::new();
    }

    let mut clusters = Vec::new();
    let mut current_cluster = vec![positions[0]];

    for &pos in &positions[1..] {
        if pos - current_cluster.last().unwrap() <= max_gap {
            current_cluster.push(pos);
        } else {
            let mean = current_cluster.iter().sum::<i32>() / current_cluster.len() as i32;
            clusters.push(mean);
            current_cluster = vec![pos];
        }
    }

    let mean = current_cluster.iter().sum::<i32>() / current_cluster.len() as i32;
    clusters.push(mean);

    clusters
}

// ---------------------------------------------------------------------------
// Color validation — reject Pickups charts (cyan bars) vs daily (blue bars)
// ---------------------------------------------------------------------------

use crate::image_utils::rgb_to_hsv;

/// HSV hue ranges (OpenCV convention: H 0-180)
const BLUE_HUE_MIN: u8 = 100;
const BLUE_HUE_MAX: u8 = 130;
const CYAN_HUE_MIN: u8 = 80;
const _CYAN_HUE_MAX: u8 = 100; // used as BLUE_HUE_MIN boundary in validate_bar_colors
const COLOR_MIN_SATURATION: u8 = 50;
const COLOR_MIN_VALUE: u8 = 50;
const MIN_BLUE_RATIO: f64 = 0.5;

/// Validate that a region contains blue bars (daily chart) not cyan (pickups).
///
/// Port of Python `ColorValidationStrategy.validate_region()`.
/// Returns (is_daily, confidence).
pub fn validate_bar_colors(
    img: &RgbImage,
    x_start: u32,
    width: u32,
    y_start: u32,
    y_end: u32,
) -> (bool, f64) {
    let (img_w, img_h) = img.dimensions();
    let raw = img.as_raw();
    let stride = img_w as usize * 3;

    let mut blue_count = 0u32;
    let mut cyan_count = 0u32;

    let x_end = (x_start + width).min(img_w);
    let y_end = y_end.min(img_h);

    for y in y_start..y_end {
        let row_off = y as usize * stride;
        for x in x_start..x_end {
            let idx = row_off + x as usize * 3;
            let (h, s, v) = rgb_to_hsv(raw[idx], raw[idx + 1], raw[idx + 2]);

            // Only consider colored pixels
            if s < COLOR_MIN_SATURATION || v < COLOR_MIN_VALUE {
                continue;
            }

            if h >= BLUE_HUE_MIN && h <= BLUE_HUE_MAX {
                blue_count += 1;
            } else if h >= CYAN_HUE_MIN && h < BLUE_HUE_MIN {
                cyan_count += 1;
            }
        }
    }

    let total = blue_count + cyan_count;

    if total == 0 {
        // No blue or cyan bars — might be empty chart or gray bars, allow it
        return (true, 0.6);
    }

    let blue_ratio = blue_count as f64 / total as f64;
    let is_daily = blue_ratio >= MIN_BLUE_RATIO;

    let confidence = if is_daily {
        (0.7 + (blue_ratio - MIN_BLUE_RATIO) * 0.6).min(0.99)
    } else {
        0.0
    };

    (is_daily, confidence)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cluster_positions() {
        let positions = vec![10, 11, 12, 30, 31, 50];
        let clusters = cluster_positions(&positions, 3);
        assert_eq!(clusters.len(), 3);
        assert_eq!(clusters[0], 11);
        assert_eq!(clusters[1], 30);
        assert_eq!(clusters[2], 50);
    }

    #[test]
    fn test_cluster_positions_empty() {
        let clusters = cluster_positions(&[], 3);
        assert!(clusters.is_empty());
    }

    #[test]
    fn test_cluster_positions_single() {
        let clusters = cluster_positions(&[42], 3);
        assert_eq!(clusters, vec![42]);
    }

    #[test]
    fn test_fast_luma() {
        assert_eq!(fast_luma(255, 255, 255), 255);
        assert_eq!(fast_luma(0, 0, 0), 0);
        assert_eq!(fast_luma(200, 200, 200), 200);
    }
}
