//! Grid detection strategies for locating the bar chart region.
//!
//! Supports multiple detection methods:
//! - Line-based: visual pattern detection (horizontal/vertical lines)
//! - OCR-anchored: text anchor detection ("12 AM", "60")
//! - Lookup: resolution-based lookup table
//! - Manual: user-provided coordinates

pub mod line_based;
pub mod lookup;
pub mod ocr_anchored;
pub mod strategies;

use crate::types::{DetectionMethod, GridBounds, GridDetectionResult, ProcessingError};
use image::RgbImage;

/// Detect grid bounds using the specified method.
pub fn detect_grid(
    img: &RgbImage,
    method: DetectionMethod,
) -> Result<GridDetectionResult, ProcessingError> {
    detect_grid_with_original(img, method, None)
}

/// Detect grid bounds, with optional original image for dark mode OCR fallback.
pub fn detect_grid_with_original(
    img: &RgbImage,
    method: DetectionMethod,
    original_img: Option<&RgbImage>,
) -> Result<GridDetectionResult, ProcessingError> {
    match method {
        DetectionMethod::LineBased => line_based::detect(img),
        DetectionMethod::OcrAnchored => ocr_anchored::detect_with_original(img, original_img),
        DetectionMethod::Manual => Err(ProcessingError::GridDetection(
            "Manual detection requires user-provided coordinates".to_string(),
        )),
    }
}

/// Calculate ROI from user-provided click coordinates.
///
/// Port of Python `calculate_roi_from_clicks()`.
pub fn calculate_roi_from_clicks(
    upper_left: [i32; 2],
    lower_right: [i32; 2],
    img_width: u32,
    img_height: u32,
) -> Result<GridBounds, ProcessingError> {
    if upper_left[0] < 0 || upper_left[1] < 0 || lower_right[0] < 0 || lower_right[1] < 0 {
        return Err(ProcessingError::InvalidRoi(
            "Coordinates cannot be negative".to_string(),
        ));
    }

    let roi_width = lower_right[0] - upper_left[0];
    let roi_height = lower_right[1] - upper_left[1];

    if roi_width <= 0 || roi_height <= 0 {
        return Err(ProcessingError::InvalidRoi(format!(
            "Invalid region dimensions: width={roi_width}, height={roi_height}"
        )));
    }

    if upper_left[0] as u32 >= img_width || upper_left[1] as u32 >= img_height {
        return Err(ProcessingError::InvalidRoi(format!(
            "Upper left ({}, {}) exceeds image bounds ({img_width}, {img_height})",
            upper_left[0], upper_left[1]
        )));
    }

    if lower_right[0] as u32 > img_width || lower_right[1] as u32 > img_height {
        return Err(ProcessingError::InvalidRoi(format!(
            "Lower right ({}, {}) exceeds image bounds ({img_width}, {img_height})",
            lower_right[0], lower_right[1]
        )));
    }

    Ok(GridBounds::new(
        upper_left[0],
        upper_left[1],
        lower_right[0],
        lower_right[1],
    ))
}

/// Calculate ROI from anchor positions.
///
/// Port of Python `calculate_roi()`.
pub fn calculate_roi(
    lower_left_x: i32,
    upper_right_y: i32,
    roi_width: i32,
    roi_height: i32,
    img_width: u32,
    img_height: u32,
) -> Result<GridBounds, ProcessingError> {
    if lower_left_x < 0 {
        return Err(ProcessingError::InvalidRoi(format!(
            "Invalid ROI lower left x: {lower_left_x}"
        )));
    }
    if upper_right_y < 0 {
        return Err(ProcessingError::InvalidRoi(format!(
            "Invalid ROI upper right y: {upper_right_y}"
        )));
    }
    if roi_width <= 0 || roi_height <= 0 {
        return Err(ProcessingError::InvalidRoi(format!(
            "Invalid ROI dimensions: {roi_width}x{roi_height}"
        )));
    }
    if lower_left_x as u32 >= img_width {
        return Err(ProcessingError::InvalidRoi(format!(
            "ROI x {lower_left_x} exceeds image width {img_width}"
        )));
    }
    if upper_right_y as u32 >= img_height {
        return Err(ProcessingError::InvalidRoi(format!(
            "ROI y {upper_right_y} exceeds image height {img_height}"
        )));
    }
    if lower_left_x + roi_width > img_width as i32 {
        return Err(ProcessingError::InvalidRoi(format!(
            "ROI extends beyond image width: {} > {img_width}",
            lower_left_x + roi_width
        )));
    }
    if upper_right_y + roi_height > img_height as i32 {
        return Err(ProcessingError::InvalidRoi(format!(
            "ROI extends beyond image height: {} > {img_height}",
            upper_right_y + roi_height
        )));
    }

    Ok(GridBounds::from_roi(
        lower_left_x,
        upper_right_y,
        roi_width,
        roi_height,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_calculate_roi_from_clicks_valid() {
        let result = calculate_roi_from_clicks([10, 20], [100, 200], 500, 500);
        assert!(result.is_ok());
        let b = result.unwrap();
        assert_eq!(b.width(), 90);
        assert_eq!(b.height(), 180);
    }

    #[test]
    fn test_calculate_roi_from_clicks_negative() {
        let result = calculate_roi_from_clicks([-1, 0], [100, 100], 500, 500);
        assert!(result.is_err());
    }

    #[test]
    fn test_calculate_roi_from_clicks_inverted() {
        let result = calculate_roi_from_clicks([100, 100], [10, 10], 500, 500);
        assert!(result.is_err());
    }

    #[test]
    fn test_calculate_roi_valid() {
        let result = calculate_roi(10, 20, 100, 50, 500, 500);
        assert!(result.is_ok());
        let b = result.unwrap();
        assert_eq!(b.roi_x(), 10);
        assert_eq!(b.roi_y(), 20);
        assert_eq!(b.width(), 100);
        assert_eq!(b.height(), 50);
    }

    #[test]
    fn test_calculate_roi_out_of_bounds() {
        let result = calculate_roi(400, 20, 200, 50, 500, 500);
        assert!(result.is_err());
    }
}
