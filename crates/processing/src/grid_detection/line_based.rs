//! Line-based grid detector — finds the chart using visual line patterns.
//!
//! Port of Python line_based_detection/detector.py and combined.py.
//! This is the recommended detection method (no OCR dependency).

use image::RgbImage;

use super::lookup;
use super::strategies::{
    fast_luma, find_evenly_spaced_groups, find_horizontal_lines, validate_bar_colors,
    validate_vertical_lines,
};
use crate::types::{GridBounds, GridDetectionResult, ProcessingError};

/// Gray value range for grid edge detection.
const GRID_LINE_GRAY_MIN: u8 = 190;
const GRID_LINE_GRAY_MAX: u8 = 220;

/// Detect grid using the combined line-based strategy.
///
/// Steps:
/// 1. Get x, width, height from resolution lookup table
/// 2. Find horizontal line groups
/// 3. Validate with vertical line count (4-5 = daily, 7+ = weekly)
/// 4. Refine x boundaries using actual grid edges
/// Detect grid using the combined line-based strategy.
///
/// IMPORTANT: Caller must have already applied `convert_dark_mode()` to the image.
/// This function does NOT clone or re-convert the image.
pub fn detect(img: &RgbImage) -> Result<GridDetectionResult, ProcessingError> {
    let (w, h) = img.dimensions();
    let resolution = format!("{w}x{h}");

    // Step 1: Lookup table for approximate bounds
    let partial = match lookup::get_partial_bounds(w, h) {
        Some(p) => p,
        None => {
            return Ok(GridDetectionResult {
                success: false,
                bounds: None,
                confidence: 0.0,
                method: "line_based".to_string(),
                error: Some(format!("Resolution {resolution} not supported")),
            });
        }
    };

    let (x_start, width, expected_height) = (partial.0 as u32, partial.1 as u32, partial.2);

    // Step 2: Find horizontal lines
    let x_end = (x_start + width).min(w);
    let lines = find_horizontal_lines(&img, x_start, x_end);

    if lines.len() < 4 {
        return Ok(GridDetectionResult {
            success: false,
            bounds: None,
            confidence: 0.0,
            method: "line_based".to_string(),
            error: Some(format!(
                "Only found {} horizontal lines (need 4+)",
                lines.len()
            )),
        });
    }

    // Step 3: Find evenly-spaced groups and validate with vertical lines
    let groups = find_evenly_spaced_groups(&lines, Some(expected_height));

    if groups.is_empty() {
        return Ok(GridDetectionResult {
            success: false,
            bounds: None,
            confidence: 0.0,
            method: "line_based".to_string(),
            error: Some("No evenly-spaced horizontal line groups found".to_string()),
        });
    }

    // Try each candidate region: vertical line validation + color validation
    let mut best_result: Option<(GridBounds, f64, Vec<i32>)> = None;

    for group in &groups {
        let y_start = group.y_start as u32;
        let y_end = group.y_end as u32;

        // Step 3a: Validate vertical line pattern (daily = 3-5 lines)
        let (is_daily, confidence, _v_count, v_positions) =
            validate_vertical_lines(&img, x_start, width, y_start, y_end);

        if !is_daily {
            continue;
        }

        // Step 3b: Color validation — reject pickups charts (cyan bars)
        let (color_valid, _color_conf) = validate_bar_colors(&img, x_start, width, y_start, y_end);
        if !color_valid {
            continue;
        }

        if best_result.is_none() || confidence > best_result.as_ref().unwrap().1 {
            let bounds = GridBounds::from_roi(
                x_start as i32,
                y_start as i32,
                width as i32,
                (y_end - y_start) as i32,
            );
            best_result = Some((bounds, confidence, v_positions));
        }
    }

    match best_result {
        Some((bounds, confidence, v_positions)) => {
            // Step 4: Refine x boundaries
            let refined = refine_x_boundaries(&img, &bounds, &v_positions);

            Ok(GridDetectionResult {
                success: true,
                bounds: Some(refined),
                confidence,
                method: "line_based".to_string(),
                error: None,
            })
        }
        None => {
            // No candidate passed vertical validation — could be a weekly chart.
            // Return failure instead of silently returning an unvalidated region.
            Ok(GridDetectionResult {
                success: false,
                bounds: None,
                confidence: 0.0,
                method: "line_based".to_string(),
                error: Some(
                    "Horizontal lines found but no region matches daily chart vertical pattern (may be weekly chart)".to_string()
                ),
            })
        }
    }
}

/// Refine x boundaries by detecting actual grid edges.
fn refine_x_boundaries(img: &RgbImage, bounds: &GridBounds, v_positions: &[i32]) -> GridBounds {
    let (w, _h) = img.dimensions();

    let search_margin = 50i32;
    let search_x_start = (bounds.upper_left_x - search_margin).max(0) as u32;
    let search_x_end = ((bounds.lower_right_x + search_margin) as u32).min(w);

    let y_start = bounds.upper_left_y as u32;
    let y_end = bounds.lower_right_y as u32;

    // Find vertical grid lines at edges
    if let Some((left, right)) = find_grid_edges(img, search_x_start, search_x_end, y_start, y_end)
    {
        return GridBounds::new(left, bounds.upper_left_y, right, bounds.lower_right_y);
    }

    // Fallback: extrapolate from vertical line positions
    if v_positions.len() >= 3 {
        let spacings: Vec<i32> = v_positions.windows(2).map(|w| w[1] - w[0]).collect();
        let mean_spacing = spacings.iter().sum::<i32>() as f64 / spacings.len() as f64;

        let left_edge = (v_positions[0] as f64 - mean_spacing) as i32 + bounds.upper_left_x;
        let right_edge =
            (*v_positions.last().unwrap() as f64 + mean_spacing) as i32 + bounds.upper_left_x;

        let left_edge = left_edge.max(0);
        let right_edge = (right_edge as u32).min(w) as i32;

        if right_edge > left_edge {
            return GridBounds::new(
                left_edge,
                bounds.upper_left_y,
                right_edge,
                bounds.lower_right_y,
            );
        }
    }

    *bounds
}

/// Find left and right grid edges by detecting vertical lines.
/// Uses direct RGB buffer access with inline luma computation.
fn find_grid_edges(
    img: &RgbImage,
    x_start: u32,
    x_end: u32,
    y_start: u32,
    y_end: u32,
) -> Option<(i32, i32)> {
    let region_h = y_end.saturating_sub(y_start);
    if region_h == 0 {
        return None;
    }

    let (w, h) = img.dimensions();
    let raw = img.as_raw();
    let stride = w as usize * 3;
    let min_coverage = 0.3f64;
    let threshold = (region_h as f64 * min_coverage) as u32;
    let mut positions = Vec::new();

    for x in x_start..x_end.min(w) {
        let mut count = 0u32;
        for y in y_start..y_end.min(h) {
            let idx = y as usize * stride + x as usize * 3;
            let luma = fast_luma(raw[idx], raw[idx + 1], raw[idx + 2]);
            if luma >= GRID_LINE_GRAY_MIN && luma <= GRID_LINE_GRAY_MAX {
                count += 1;
            }
        }
        if count >= threshold {
            positions.push(x as i32);
        }
    }

    if positions.len() < 2 {
        return None;
    }

    // Cluster
    let clusters = super::strategies::cluster_positions(&positions, 3);
    if clusters.len() < 2 {
        return None;
    }

    // Pick the cluster closest to x_start as the left edge,
    // and the cluster closest to x_end as the right edge.
    // Using first/last would pick up gray UI elements at the extreme
    // edges of the search window as false grid boundaries.
    let x_start_i = x_start as i32;
    let x_end_i = x_end as i32;
    let left = *clusters.iter().min_by_key(|&&c| (c - x_start_i).abs()).unwrap();
    let right = *clusters.iter().min_by_key(|&&c| (c - x_end_i).abs()).unwrap();

    if right <= left {
        return None;
    }

    Some((left, right))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_unsupported_resolution() {
        let img = RgbImage::new(100, 100);
        let result = detect(&img).unwrap();
        assert!(!result.success);
        assert!(result.error.unwrap().contains("not supported"));
    }
}
