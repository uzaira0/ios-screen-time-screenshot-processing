//! Full image processing pipeline orchestration.
//!
//! Port of Python image_processor.py — ties together all processing stages:
//! dark mode conversion, grid detection, bar extraction, OCR, and alignment scoring.

use std::{path::Path, time::Instant};

use image::RgbImage;
use log::info;

#[cfg(feature = "ocr")]
use super::ocr;
use super::{
    bar_extraction::{compute_bar_alignment_score, slice_image},
    boundary_optimizer::optimize_boundaries,
    grid_detection,
    image_utils::{convert_dark_mode, remove_all_but},
    types::{DetectionMethod, GridBounds, ImageType, ProcessingError, ProcessingResult},
};

/// Load an image from disk and convert to RGB.
fn load_image(path: &str) -> Result<RgbImage, ProcessingError> {
    let img = image::open(path)?;
    Ok(img.to_rgb8())
}

/// Load image and apply dark mode conversion.
fn load_and_prepare(path: &str) -> Result<RgbImage, ProcessingError> {
    let mut img = load_image(path)?;
    convert_dark_mode(&mut img);
    Ok(img)
}

/// Extract bar values and compute alignment score for given bounds.
/// Returns (hourly_values_24, total, alignment_score).
fn extract_and_score(
    img: &RgbImage,
    bounds: &GridBounds,
    image_type: ImageType,
) -> (Vec<f64>, f64, f64) {
    let roi_x = bounds.roi_x() as u32;
    let roi_y = bounds.roi_y() as u32;
    let roi_w = bounds.width() as u32;
    let roi_h = bounds.height() as u32;

    // For battery images, apply color isolation to a copy of the ROI only (not full image).
    // Canvas order: orange [255, 121, 0] first, blue [0, 134, 255] fallback.
    // Fallback condition: inverted_sum of ROI < 10 (canvas: darkBlueSum < 10),
    // meaning no orange pixels were found (all pixels white after filter).
    let hourly_row = if image_type == ImageType::Battery {
        let roi_base = image::imageops::crop_imm(img, roi_x, roi_y, roi_w, roi_h).to_image();
        let mut roi = roi_base.clone();
        remove_all_but(&mut roi, [255, 121, 0], 30);
        let inverted_sum: u32 = roi.as_raw().iter().map(|&p| 255u32 - p as u32).sum();
        if inverted_sum < 10 {
            let mut roi2 = roi_base;
            remove_all_but(&mut roi2, [0, 134, 255], 30);
            slice_image(&roi2, 0, 0, roi_w, roi_h)
        } else {
            slice_image(&roi, 0, 0, roi_w, roi_h)
        }
    } else {
        slice_image(img, roi_x, roi_y, roi_w, roi_h)
    };

    // Ensure we have at least 24 values (slice_image returns 25: 24 hours + total)
    let hourly_values = if hourly_row.len() > 24 {
        hourly_row[..24].to_vec()
    } else {
        let mut v = hourly_row.clone();
        v.resize(24, 0.0);
        v
    };

    let total: f64 = hourly_values.iter().sum();

    // Compute alignment score using original (non-binarized) ROI
    let roi_original = image::imageops::crop_imm(img, roi_x, roi_y, roi_w, roi_h).to_image();
    let alignment_score = compute_bar_alignment_score(&roi_original, &hourly_values);

    (hourly_values, total, alignment_score)
}

/// Process a screenshot with automatic grid detection.
pub fn process_image(
    path: &str,
    image_type: ImageType,
    detection_method: DetectionMethod,
) -> Result<ProcessingResult, ProcessingError> {
    let start = Instant::now();
    let original_img = load_image(path)?;
    let mut img = original_img.clone();
    convert_dark_mode(&mut img);

    // OCR first — needed for daily total check and always available even on grid failure
    #[cfg(feature = "ocr")]
    let (title, _title_y, total_text) = ocr::find_title_and_total(&img)?;
    #[cfg(not(feature = "ocr"))]
    let (title, _title_y, total_text): (String, Option<i32>, String) =
        (String::new(), None, String::new());
    let is_daily_total = title == "Daily Total";

    // Don't skip daily total pages — they still have bar charts (all apps combined).
    // The is_daily_total flag is propagated so callers can decide to skip or use the data.

    // Detect grid bounds (pass original for dark mode OCR fallback)
    let grid_result =
        grid_detection::detect_grid_with_original(&img, detection_method, Some(&original_img))?;

    let bounds = match (grid_result.success, grid_result.bounds) {
        (true, Some(b)) => b,
        _ => {
            return Err(ProcessingError::GridDetection(
                grid_result
                    .error
                    .unwrap_or_else(|| "Grid detection failed".to_string()),
            ));
        }
    };

    let (hourly_values, total, alignment_score) = extract_and_score(&img, &bounds, image_type);

    let elapsed = start.elapsed().as_millis() as u64;
    info!(
        "Processed {} in {elapsed}ms (method={}, title='{}', total_text='{}', alignment={alignment_score:.2})",
        Path::new(path)
            .file_name()
            .unwrap_or_default()
            .to_string_lossy(),
        grid_result.method,
        title,
        total_text,
    );

    Ok(ProcessingResult {
        hourly_values: Some(hourly_values),
        total,
        title: if title.is_empty() { None } else { Some(title) },
        total_text: if total_text.is_empty() {
            None
        } else {
            Some(total_text)
        },
        grid_bounds: Some(bounds),
        alignment_score: Some(alignment_score),
        detection_method: grid_result.method,
        processing_time_ms: elapsed,
        is_daily_total,
        issues: vec![],
        has_blocking_issues: false,
        grid_detection_confidence: Some(grid_result.confidence),
        title_y_position: _title_y,
    })
}

/// Process a screenshot with user-provided grid coordinates.
pub fn process_image_with_grid(
    path: &str,
    upper_left: [i32; 2],
    lower_right: [i32; 2],
    image_type: ImageType,
) -> Result<ProcessingResult, ProcessingError> {
    let start = Instant::now();
    let img = load_and_prepare(path)?;
    let (w, h) = img.dimensions();

    let bounds = grid_detection::calculate_roi_from_clicks(upper_left, lower_right, w, h)?;
    let (hourly_values, total, alignment_score) = extract_and_score(&img, &bounds, image_type);

    #[cfg(feature = "ocr")]
    let (title, _title_y, total_text) = ocr::find_title_and_total(&img)?;
    #[cfg(not(feature = "ocr"))]
    let (title, _title_y, total_text): (String, Option<i32>, String) =
        (String::new(), None, String::new());
    let is_daily_total = title == "Daily Total";
    Ok(ProcessingResult {
        hourly_values: Some(hourly_values),
        total,
        title: if title.is_empty() { None } else { Some(title) },
        total_text: if total_text.is_empty() {
            None
        } else {
            Some(total_text)
        },
        grid_bounds: Some(bounds),
        alignment_score: Some(alignment_score),
        detection_method: "manual".to_string(),
        processing_time_ms: start.elapsed().as_millis() as u64,
        is_daily_total,
        issues: vec![],
        has_blocking_issues: false,
        grid_detection_confidence: None,
        title_y_position: _title_y,
    })
}

/// Process with automatic grid detection + boundary optimization.
///
/// Runs the full pipeline then fine-tunes the detected grid bounds by trying
/// small shifts to minimise the difference between extracted bar totals and
/// the OCR total string.
///
/// If `detection_method` is `LineBased` and grid detection fails, automatically
/// retries with `OcrAnchored` before returning an error.
pub fn process_image_optimized(
    path: &str,
    image_type: ImageType,
    detection_method: DetectionMethod,
    max_shift: i32,
) -> Result<ProcessingResult, ProcessingError> {
    let start = Instant::now();
    let original_img = load_image(path)?;
    let mut img = original_img.clone();
    convert_dark_mode(&mut img);

    // OCR once — needed for daily total check and optimizer.
    #[cfg(feature = "ocr")]
    let (title, _title_y, total_text) = ocr::find_title_and_total(&img)?;
    #[cfg(not(feature = "ocr"))]
    let (title, _title_y, total_text): (String, Option<i32>, String) =
        (String::new(), None, String::new());
    let is_daily_total = title == "Daily Total";

    // Don't skip — daily total pages still have bar charts. Propagate the flag instead.

    // Grid detection — fall back from line_based to ocr_anchored automatically.
    let grid_result =
        grid_detection::detect_grid_with_original(&img, detection_method, Some(&original_img))?;

    let initial_bounds = if grid_result.success {
        grid_result.bounds.unwrap()
    } else if detection_method == DetectionMethod::LineBased {
        // line_based found nothing — try ocr_anchored before giving up (native only).
        #[cfg(feature = "ocr")]
        {
            let fallback = grid_detection::detect_grid_with_original(
                &img,
                DetectionMethod::OcrAnchored,
                Some(&original_img),
            )?;
            match (fallback.success, fallback.bounds) {
                (true, Some(b)) => b,
                _ => {
                    return Err(ProcessingError::GridDetection(
                        fallback.error.unwrap_or_else(|| {
                            "Grid detection failed (line_based + ocr_anchored)".to_string()
                        }),
                    ));
                }
            }
        }
        #[cfg(not(feature = "ocr"))]
        return Err(ProcessingError::GridDetection(
            grid_result
                .error
                .unwrap_or_else(|| "Grid detection failed (line_based)".to_string()),
        ));
    } else {
        return Err(ProcessingError::GridDetection(
            grid_result
                .error
                .unwrap_or_else(|| "Grid detection failed".to_string()),
        ));
    };

    // Boundary optimization
    let opt = optimize_boundaries(&img, &initial_bounds, &total_text, max_shift, image_type);
    let bounds = opt.bounds;

    let (hourly_values, total, alignment_score) = extract_and_score(&img, &bounds, image_type);

    let elapsed = start.elapsed().as_millis() as u64;
    info!(
        "Processed (optimized) {} in {elapsed}ms (method={}, shift=({},{},{}), converged={}, title='{}', total_text='{}', is_daily_total={is_daily_total})",
        Path::new(path)
            .file_name()
            .unwrap_or_default()
            .to_string_lossy(),
        grid_result.method,
        opt.shift_x,
        opt.shift_y,
        opt.shift_width,
        opt.converged,
        title,
        total_text,
    );

    Ok(ProcessingResult {
        hourly_values: Some(hourly_values),
        total,
        title: if title.is_empty() { None } else { Some(title) },
        total_text: if total_text.is_empty() {
            None
        } else {
            Some(total_text)
        },
        grid_bounds: Some(bounds),
        alignment_score: Some(alignment_score),
        detection_method: grid_result.method,
        processing_time_ms: elapsed,
        is_daily_total,
        issues: vec![],
        has_blocking_issues: false,
        grid_detection_confidence: Some(grid_result.confidence),
        title_y_position: _title_y,
    })
}

/// Extract only hourly data (skip OCR, fast path).
pub fn extract_hourly_data(
    path: &str,
    upper_left: [i32; 2],
    lower_right: [i32; 2],
    image_type: ImageType,
) -> Result<Vec<f64>, ProcessingError> {
    let img = load_and_prepare(path)?;
    let (w, h) = img.dimensions();
    let bounds = grid_detection::calculate_roi_from_clicks(upper_left, lower_right, w, h)?;

    let hourly_row = if image_type == ImageType::Battery {
        let roi_x = bounds.roi_x() as u32;
        let roi_y = bounds.roi_y() as u32;
        let roi_w = bounds.width() as u32;
        let roi_h = bounds.height() as u32;
        let roi_base = image::imageops::crop_imm(&img, roi_x, roi_y, roi_w, roi_h).to_image();
        let mut roi = roi_base.clone();
        remove_all_but(&mut roi, [255, 121, 0], 30);
        let inverted_sum: u32 = roi.as_raw().iter().map(|&p| 255u32 - p as u32).sum();
        if inverted_sum < 10 {
            let mut roi2 = roi_base;
            remove_all_but(&mut roi2, [0, 134, 255], 30);
            slice_image(&roi2, 0, 0, roi_w, roi_h)
        } else {
            slice_image(&roi, 0, 0, roi_w, roi_h)
        }
    } else {
        slice_image(
            &img,
            bounds.roi_x() as u32,
            bounds.roi_y() as u32,
            bounds.width() as u32,
            bounds.height() as u32,
        )
    };

    Ok(hourly_row)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_and_score_white_image() {
        let img = RgbImage::from_fn(240, 100, |_, _| image::Rgb([255, 255, 255]));
        let bounds = GridBounds::from_roi(0, 0, 240, 100);
        let (values, total, _score) = extract_and_score(&img, &bounds, ImageType::ScreenTime);
        assert_eq!(values.len(), 24);
        assert!(total.abs() < 0.01);
    }
}
