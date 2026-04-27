//! OCR-anchored grid detector — finds "12 AM" and "60" text anchors.
//!
//! Port of Python grid_anchors.py + ocr_integration.py.
//! Uses leptess (Tesseract binding) to find text anchors that mark
//! the grid boundaries, then calculates the ROI from their positions.

use image::RgbImage;
use log::{debug, info};

use super::calculate_roi;
use crate::{
    image_utils::{
        adjust_contrast_brightness, convert_dark_mode_for_ocr, extract_line, get_pixel,
        is_dark_mode,
    },
    ocr::{OcrWord, run_tesseract},
    types::{GridDetectionResult, ProcessingError},
};

/// Prepare left and right image chunks for OCR anchor detection.
///
/// Port of Python `prepare_image_chunks()`.
fn prepare_image_chunks(img: &RgbImage) -> (RgbImage, RgbImage, u32) {
    let (img_w, img_h) = img.dimensions();
    let chunk_num = 3u32;
    let top_removal = (img_h as f64 * 0.05) as u32;
    let chunk_w = img_w / chunk_num;

    // Left chunk: first 1/3
    let mut img_left = image::imageops::crop_imm(img, 0, 0, chunk_w, img_h).to_image();
    // Right chunk: last 1/3
    let mut img_right =
        image::imageops::crop_imm(img, img_w - chunk_w, 0, chunk_w, img_h).to_image();

    // Blank out top 5% with most common pixel (removes status bar)
    if let Some(bg) = get_pixel(&img_left, 1) {
        for y in 0..top_removal.min(img_h) {
            for x in 0..chunk_w {
                img_left.put_pixel(x, y, image::Rgb(bg));
            }
        }
    }
    if let Some(bg) = get_pixel(&img_right, 1) {
        for y in 0..top_removal.min(img_h) {
            for x in 0..chunk_w {
                img_right.put_pixel(x, y, image::Rgb(bg));
            }
        }
    }

    let right_offset = img_w - chunk_w;
    (img_left, img_right, right_offset)
}

/// Find the "12AM" anchor on the left side of the graph.
///
/// Port of Python `find_left_anchor()`.
fn find_left_anchor(
    ocr_boxes: &[OcrWord],
    img: &RgbImage,
    detections_to_skip: usize,
) -> Option<(i32, i32)> {
    let buffer = 25i32;
    let max_offset = 100;
    let keys = ["2A", "12", "AM"];
    let (img_w, _img_h) = img.dimensions();

    let mut detection_count = 0usize;

    for b in ocr_boxes {
        let text_upper = b.text.to_uppercase();
        if !keys.iter().any(|k| text_upper.contains(k)) {
            continue;
        }

        detection_count += 1;
        if detection_count <= detections_to_skip {
            continue;
        }

        let (x, y, w, h) = (b.x, b.y, b.w, b.h);

        // Move up to find horizontal grid line
        for offset in 0..max_offset {
            let x0 = (x - buffer).max(0) as u32;
            let x1 = ((x + w + buffer) as u32).min(img_w);
            let y0 = (y - offset as i32 - buffer).max(0) as u32;
            let y1 = ((y - offset as i32 + buffer) as u32).min(img.height());
            if x1 <= x0 || y1 <= y0 {
                continue;
            }
            let row = extract_line(img, x0, x1, y0, y1, true);
            if row > 0 {
                let lower_left_y = y - buffer + row as i32 - offset as i32;

                // Move left to find vertical grid line
                for v_offset in 0..max_offset {
                    let vx0 = (x - v_offset as i32 - buffer).max(0) as u32;
                    let vx1 = ((x - v_offset as i32 + buffer) as u32).min(img_w);
                    let vy0 = (y - buffer).max(0) as u32;
                    let vy1 = y.max(0) as u32;
                    if vx1 <= vx0 || vy1 <= vy0 {
                        continue;
                    }
                    let col = extract_line(img, vx0, vx1, vy0, vy1, false);
                    if col > 0 {
                        let lower_left_x = x - buffer + col as i32 - v_offset as i32;
                        info!(
                            "Found left anchor '12AM' at ({lower_left_x}, {lower_left_y}) from text '{}' at ({x},{y})",
                            b.text
                        );
                        return Some((lower_left_x, lower_left_y));
                    }
                }

                // Fallback: use x position directly
                return Some((x - buffer, lower_left_y));
            }
        }

        // If loop completed without finding a grid line, use text position as approximation
        return Some((x - buffer, y + h));
    }

    None
}

/// Find the "60" anchor on the right side of the graph.
///
/// Port of Python `find_right_anchor()`.
fn find_right_anchor(ocr_boxes: &[OcrWord], img: &RgbImage) -> Option<(i32, i32)> {
    let buffer = 25i32;
    let max_offset = 100;
    let keys = ["60"];
    let (img_w, _img_h) = img.dimensions();

    for b in ocr_boxes {
        let text_upper = b.text.to_uppercase();
        if !keys.iter().any(|k| text_upper.contains(k)) {
            continue;
        }

        let (x, y, _w, h) = (b.x, b.y, b.w, b.h);

        // Move up to find horizontal grid line
        for offset in 0..max_offset {
            let x0 = (x - buffer).max(0) as u32;
            let x1 = (x as u32).min(img_w);
            let y0 = (y - offset as i32).max(0) as u32;
            let y1 = ((y - offset as i32 + h + buffer) as u32).min(img.height());
            if x1 <= x0 || y1 <= y0 {
                continue;
            }
            let row = extract_line(img, x0, x1, y0, y1, true);
            if row > 0 {
                let upper_right_y = y + row as i32 - offset as i32;

                // Move left to find vertical grid line
                for v_offset in 0..max_offset {
                    let vx0 = (x - buffer - v_offset as i32).max(0) as u32;
                    let vx1 = ((x - v_offset as i32) as u32).min(img_w);
                    let vy0 = y.max(0) as u32;
                    let vy1 = ((y + h + buffer) as u32).min(img.height());
                    if vx1 <= vx0 || vy1 <= vy0 {
                        continue;
                    }
                    let col = extract_line(img, vx0, vx1, vy0, vy1, false);
                    if col > 0 {
                        let upper_right_x = x - buffer + col as i32 - v_offset as i32;
                        info!(
                            "Found right anchor '60' at ({upper_right_x}, {upper_right_y}) from text '{}' at ({x},{y})",
                            b.text
                        );
                        return Some((upper_right_x, upper_right_y));
                    }
                }

                return Some((x - buffer, upper_right_y));
            }
        }

        // Fallback: use text position
        return Some((x - buffer, y));
    }

    None
}

/// Try to find grid anchors from OCR boxes on a processed image.
///
/// Returns Some(GridDetectionResult) on success, None if anchors not found.
fn try_find_anchors(
    img_processed: &RgbImage,
) -> Result<Option<GridDetectionResult>, ProcessingError> {
    let (w, h) = img_processed.dimensions();
    let (img_left, img_right, right_offset) = prepare_image_chunks(img_processed);

    let left_boxes = run_tesseract(&img_left, "6")?;
    let mut right_boxes = run_tesseract(&img_right, "6")?;

    for b in &mut right_boxes {
        b.x += right_offset as i32;
    }

    info!(
        "OCR anchored: {} left boxes, {} right boxes",
        left_boxes.len(),
        right_boxes.len()
    );

    for skip in 0..4 {
        let left = find_left_anchor(&left_boxes, img_processed, skip);
        let right = find_right_anchor(&right_boxes, img_processed);

        if let (Some((ll_x, ll_y)), Some((ur_x, ur_y))) = (left, right) {
            let roi_width = ur_x - ll_x;
            let roi_height = ll_y - ur_y;

            match calculate_roi(ll_x, ur_y, roi_width, roi_height, w, h) {
                Ok(bounds) => {
                    info!(
                        "OCR anchored detection succeeded: ({},{}) {}x{} (skip={skip})",
                        bounds.roi_x(),
                        bounds.roi_y(),
                        bounds.width(),
                        bounds.height()
                    );
                    return Ok(Some(GridDetectionResult {
                        success: true,
                        bounds: Some(bounds),
                        confidence: 1.0,
                        method: "ocr_anchored".to_string(),
                        error: None,
                    }));
                }
                Err(e) => {
                    debug!("OCR anchor attempt skip={skip} failed: {e}");
                    continue;
                }
            }
        }
    }

    Ok(None)
}

/// Detect grid using OCR text anchors ("12 AM" and "60").
///
/// IMPORTANT: Caller must have already applied `convert_dark_mode()`.
/// Pass `original_img` (before dark mode conversion) to enable adaptive
/// threshold fallback for dark mode screenshots.
pub fn detect(img: &RgbImage) -> Result<GridDetectionResult, ProcessingError> {
    detect_with_original(img, None)
}

/// Detect grid using OCR text anchors, with optional original image for dark mode fallback.
pub fn detect_with_original(
    img: &RgbImage,
    original_img: Option<&RgbImage>,
) -> Result<GridDetectionResult, ProcessingError> {
    // Standard path: contrast/brightness for OCR readability
    let img_processed = adjust_contrast_brightness(img, 2.0, -220);

    if let Some(result) = try_find_anchors(&img_processed)? {
        return Ok(result);
    }

    // Dark mode fallback: standard preprocessing destroys faint text contrast
    // (contrast=3.0 clips both text and background to ~255). Use adaptive
    // thresholding which preserves text for Tesseract anchor detection.
    let orig = original_img.unwrap_or(img);
    if is_dark_mode(orig) {
        info!(
            "Standard anchor detection failed on dark mode image, retrying with adaptive threshold OCR"
        );
        let img_ocr = convert_dark_mode_for_ocr(orig);
        let img_ocr_processed = adjust_contrast_brightness(&img_ocr, 2.0, -220);

        if let Some(result) = try_find_anchors(&img_ocr_processed)? {
            return Ok(result);
        }
    }

    Ok(GridDetectionResult {
        success: false,
        bounds: None,
        confidence: 0.0,
        method: "ocr_anchored".to_string(),
        error: Some("Could not find graph anchors (12 AM / 60)".to_string()),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_returns_failure_on_small_image() {
        let img = RgbImage::new(100, 100);
        let result = detect(&img).unwrap();
        assert!(!result.success);
    }
}
