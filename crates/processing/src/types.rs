//! Shared types for the image processing pipeline.

use serde::{Deserialize, Serialize};

/// Grid boundary coordinates (upper-left corner + lower-right corner).
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct GridBounds {
    pub upper_left_x: i32,
    pub upper_left_y: i32,
    pub lower_right_x: i32,
    pub lower_right_y: i32,
}

impl GridBounds {
    pub fn new(
        upper_left_x: i32,
        upper_left_y: i32,
        lower_right_x: i32,
        lower_right_y: i32,
    ) -> Self {
        Self {
            upper_left_x,
            upper_left_y,
            lower_right_x,
            lower_right_y,
        }
    }

    /// Create from ROI-style (x, y, width, height).
    pub fn from_roi(x: i32, y: i32, width: i32, height: i32) -> Self {
        Self {
            upper_left_x: x,
            upper_left_y: y,
            lower_right_x: x + width,
            lower_right_y: y + height,
        }
    }

    pub fn width(&self) -> i32 {
        self.lower_right_x - self.upper_left_x
    }

    pub fn height(&self) -> i32 {
        self.lower_right_y - self.upper_left_y
    }

    pub fn roi_x(&self) -> i32 {
        self.upper_left_x
    }

    pub fn roi_y(&self) -> i32 {
        self.upper_left_y
    }
}

/// Result of grid detection.
#[derive(Debug, Clone, Serialize)]
pub struct GridDetectionResult {
    pub success: bool,
    pub bounds: Option<GridBounds>,
    pub confidence: f64,
    pub method: String,
    pub error: Option<String>,
}

/// Full pipeline processing result returned to the frontend.
#[derive(Debug, Clone, Serialize)]
pub struct ProcessingResult {
    /// 24 hourly values (minutes per hour, 0.0–60.0). None for daily total pages.
    pub hourly_values: Option<Vec<f64>>,
    /// Sum of all 24 values.
    pub total: f64,
    /// OCR-extracted app name (if available).
    pub title: Option<String>,
    /// OCR-extracted total time string (e.g. "4h 36m").
    pub total_text: Option<String>,
    /// Detected grid boundaries.
    pub grid_bounds: Option<GridBounds>,
    /// Bar alignment quality score (0.0–1.0). None for daily total pages.
    pub alignment_score: Option<f64>,
    /// Which detection method was used.
    pub detection_method: String,
    /// Wall-clock processing time in milliseconds.
    pub processing_time_ms: u64,
    /// True when OCR identified this as a Daily Total / weekly summary page.
    pub is_daily_total: bool,
    /// Processing issues encountered (e.g. grid detection failure).
    pub issues: Vec<String>,
    /// True if any issue is blocking (e.g. no grid detected).
    pub has_blocking_issues: bool,
    /// Grid detection confidence score (0.0–1.0).
    pub grid_detection_confidence: Option<f64>,
    /// Y position of the title text (used for downstream layout).
    pub title_y_position: Option<i32>,
}

/// Processing pipeline errors.
#[derive(Debug, thiserror::Error)]
pub enum ProcessingError {
    #[error("Image load error: {0}")]
    ImageLoad(String),

    #[error("Grid detection failed: {0}")]
    GridDetection(String),

    #[error("Invalid ROI: {0}")]
    InvalidRoi(String),

    #[error("OCR error: {0}")]
    Ocr(String),

    #[error("Processing error: {0}")]
    General(String),
}

impl From<image::ImageError> for ProcessingError {
    fn from(e: image::ImageError) -> Self {
        ProcessingError::ImageLoad(e.to_string())
    }
}

/// Image type being processed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ImageType {
    ScreenTime,
    Battery,
}

impl ImageType {
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Self {
        match s {
            "battery" => ImageType::Battery,
            _ => ImageType::ScreenTime,
        }
    }
}

/// Grid detection method to use.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DetectionMethod {
    LineBased,
    OcrAnchored,
    Manual,
}

impl DetectionMethod {
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Self {
        match s {
            "ocr_anchored" => DetectionMethod::OcrAnchored,
            "manual" => DetectionMethod::Manual,
            _ => DetectionMethod::LineBased,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            DetectionMethod::LineBased => "line_based",
            DetectionMethod::OcrAnchored => "ocr_anchored",
            DetectionMethod::Manual => "manual",
        }
    }
}
