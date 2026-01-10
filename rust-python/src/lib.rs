//! PyO3 Python extension module for Rust-native image processing.
//!
//! Provides the same processing functions as the Tauri desktop app,
//! callable directly from Python for 30x speedup over the pure-Python pipeline.
//!
//! Usage:
//!     import screenshot_processor_rs as rs
//!     result = rs.process_image("/path/to/screenshot.png", "screen_time", "line_based")
//!     print(result["hourly_values"])  # [0.0, 0.0, ..., 15.3, ...]

use ios_screen_time_image_pipeline as processing;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::HashMap;

use processing::types::{DetectionMethod, ImageType};

/// Process a screenshot with automatic grid detection.
///
/// Args:
///     path: Path to the image file
///     image_type: "screen_time" or "battery"
///     detection_method: "line_based" or "ocr_anchored"
///
/// Returns:
///     dict with keys: hourly_values, total, title, total_text, grid_bounds,
///     alignment_score, detection_method, processing_time_ms
#[pyfunction]
#[pyo3(signature = (path, image_type="screen_time", detection_method="line_based"))]
fn process_image(
    path: &str,
    image_type: &str,
    detection_method: &str,
) -> PyResult<HashMap<String, PyObject>> {
    let img_type = ImageType::from_str(image_type);
    let method = DetectionMethod::from_str(detection_method);

    let result = processing::process_image(path, img_type, method)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    result_to_pydict(result)
}

/// Convert a ProcessingResult to a Python dict, handling Option types.
fn result_to_pydict(result: processing::types::ProcessingResult) -> PyResult<HashMap<String, PyObject>> {
    Python::with_gil(|py| {
        let mut map = HashMap::new();
        map.insert("hourly_values".to_string(), result.hourly_values.into_pyobject(py)?.into_any().unbind());
        map.insert("total".to_string(), result.total.into_pyobject(py)?.into_any().unbind());
        map.insert("title".to_string(), result.title.into_pyobject(py)?.into_any().unbind());
        map.insert("total_text".to_string(), result.total_text.into_pyobject(py)?.into_any().unbind());
        map.insert("alignment_score".to_string(), result.alignment_score.into_pyobject(py)?.into_any().unbind());
        map.insert("detection_method".to_string(), result.detection_method.into_pyobject(py)?.into_any().unbind());
        map.insert("processing_time_ms".to_string(), result.processing_time_ms.into_pyobject(py)?.into_any().unbind());
        map.insert("is_daily_total".to_string(), result.is_daily_total.into_pyobject(py)?.to_owned().into_any().unbind());
        map.insert("has_blocking_issues".to_string(), result.has_blocking_issues.into_pyobject(py)?.to_owned().into_any().unbind());
        map.insert("grid_detection_confidence".to_string(), result.grid_detection_confidence.into_pyobject(py)?.into_any().unbind());
        map.insert("title_y_position".to_string(), result.title_y_position.into_pyobject(py)?.into_any().unbind());

        // Convert Vec<String> issues to Python list
        let issues_list = pyo3::types::PyList::new(py, &result.issues)?;
        map.insert("issues".to_string(), issues_list.into_any().unbind());

        if let Some(ref bounds) = result.grid_bounds {
            let bounds_dict = PyDict::new(py);
            bounds_dict.set_item("upper_left_x", bounds.upper_left_x)?;
            bounds_dict.set_item("upper_left_y", bounds.upper_left_y)?;
            bounds_dict.set_item("lower_right_x", bounds.lower_right_x)?;
            bounds_dict.set_item("lower_right_y", bounds.lower_right_y)?;
            map.insert("grid_bounds".to_string(), bounds_dict.into_any().unbind());
        }

        Ok(map)
    })
}

/// Process a screenshot with user-provided grid coordinates.
#[pyfunction]
#[pyo3(signature = (path, upper_left, lower_right, image_type="screen_time"))]
fn process_image_with_grid(
    path: &str,
    upper_left: [i32; 2],
    lower_right: [i32; 2],
    image_type: &str,
) -> PyResult<HashMap<String, PyObject>> {
    let img_type = ImageType::from_str(image_type);

    let result = processing::process_image_with_grid(path, upper_left, lower_right, img_type)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    result_to_pydict(result)
}

/// Extract only hourly data (fast path — no OCR).
#[pyfunction]
#[pyo3(signature = (path, upper_left, lower_right, image_type="screen_time"))]
fn extract_hourly_data(
    path: &str,
    upper_left: [i32; 2],
    lower_right: [i32; 2],
    image_type: &str,
) -> PyResult<Vec<f64>> {
    let img_type = ImageType::from_str(image_type);

    processing::extract_hourly_data(path, upper_left, lower_right, img_type)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
}

/// Detect grid bounds using line-based detection.
/// Returns dict with upper_left_x, upper_left_y, lower_right_x, lower_right_y or None.
#[pyfunction]
#[pyo3(signature = (path, detection_method="line_based"))]
fn detect_grid(path: &str, detection_method: &str) -> PyResult<Option<HashMap<String, i32>>> {
    let method = DetectionMethod::from_str(detection_method);

    let img = image::open(path)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Image load: {e}")))?
        .to_rgb8();
    let mut img = img;
    processing::image_utils::convert_dark_mode(&mut img);

    let result = processing::grid_detection::detect_grid(&img, method)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    match (result.success, result.bounds) {
        (true, Some(b)) => {
            let mut map = HashMap::new();
            map.insert("upper_left_x".to_string(), b.upper_left_x);
            map.insert("upper_left_y".to_string(), b.upper_left_y);
            map.insert("lower_right_x".to_string(), b.lower_right_x);
            map.insert("lower_right_y".to_string(), b.lower_right_y);
            Ok(Some(map))
        }
        _ => Ok(None),
    }
}

/// Slice a bar graph region and extract 24 hourly values.
/// Accepts raw image bytes (PNG/JPEG) and ROI coordinates.
#[pyfunction]
fn slice_image_from_file(
    path: &str,
    roi_x: u32,
    roi_y: u32,
    roi_width: u32,
    roi_height: u32,
) -> PyResult<Vec<f64>> {
    let img = image::open(path)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Image load: {e}")))?
        .to_rgb8();
    let mut img = img;
    processing::image_utils::convert_dark_mode(&mut img);

    Ok(processing::bar_extraction::slice_image(
        &img, roi_x, roi_y, roi_width, roi_height,
    ))
}

/// Run Tesseract OCR on an image file and return word-level results.
///
/// Returns a list of dicts, each with: text, x, y, w, h, confidence.
/// Uses leptess (direct C API via set_image_from_mem) — no subprocess overhead.
#[pyfunction]
#[pyo3(signature = (image_bytes, psm="3"))]
fn ocr_extract(image_bytes: &[u8], psm: &str) -> PyResult<Vec<HashMap<String, PyObject>>> {
    // Decode image bytes to RgbImage
    let img = image::load_from_memory(image_bytes)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Image decode: {e}")))?
        .to_rgb8();

    let words = processing::ocr::run_tesseract(&img, psm)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    Python::with_gil(|py| {
        let mut result = Vec::with_capacity(words.len());
        for w in &words {
            let mut map = HashMap::new();
            map.insert("text".to_string(), w.text.as_str().into_pyobject(py)?.into_any().unbind());
            map.insert("x".to_string(), w.x.into_pyobject(py)?.into_any().unbind());
            map.insert("y".to_string(), w.y.into_pyobject(py)?.into_any().unbind());
            map.insert("w".to_string(), w.w.into_pyobject(py)?.into_any().unbind());
            map.insert("h".to_string(), w.h.into_pyobject(py)?.into_any().unbind());
            result.push(map);
        }
        Ok(result)
    })
}

/// Process a screenshot with automatic grid detection + boundary optimization.
///
/// Like process_image but also runs the boundary optimizer to fine-tune grid
/// bounds so that extracted bar totals match the OCR total string.
///
/// Args:
///     path: Path to the image file
///     image_type: "screen_time" or "battery"
///     detection_method: "line_based" or "ocr_anchored"
///     max_shift: Maximum pixels to shift grid boundaries (e.g. 5)
#[pyfunction]
#[pyo3(signature = (path, image_type="screen_time", detection_method="line_based", max_shift=5))]
fn process_image_optimized(
    path: &str,
    image_type: &str,
    detection_method: &str,
    max_shift: i32,
) -> PyResult<HashMap<String, PyObject>> {
    let img_type = ImageType::from_str(image_type);
    let method = DetectionMethod::from_str(detection_method);

    let result = processing::process_image_optimized(path, img_type, method, max_shift)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    result_to_pydict(result)
}

/// Extract time from OCR text (e.g., "4h 36m" from "some text 4h 36m more").
#[pyfunction]
fn extract_time_from_text(text: &str) -> String {
    processing::ocr::extract_time_from_text(text)
}

/// Normalize OCR digit confusions (I→1, O→0, S→5, etc.)
#[pyfunction]
fn normalize_ocr_digits(text: &str) -> String {
    processing::ocr::normalize_ocr_digits(text)
}

/// Python module definition.
#[pymodule]
fn screenshot_processor_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_image, m)?)?;
    m.add_function(wrap_pyfunction!(process_image_optimized, m)?)?;
    m.add_function(wrap_pyfunction!(process_image_with_grid, m)?)?;
    m.add_function(wrap_pyfunction!(extract_hourly_data, m)?)?;
    m.add_function(wrap_pyfunction!(detect_grid, m)?)?;
    m.add_function(wrap_pyfunction!(slice_image_from_file, m)?)?;
    m.add_function(wrap_pyfunction!(ocr_extract, m)?)?;
    m.add_function(wrap_pyfunction!(extract_time_from_text, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_ocr_digits, m)?)?;
    Ok(())
}
