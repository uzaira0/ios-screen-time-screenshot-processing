//! WebAssembly bindings for the image processing pipeline.
//!
//! Enabled with: `--features wasm --no-default-features`
//! Build:        `wasm-pack build crates/processing --target web --features wasm --no-default-features`
//!
//! # Design
//! Three responsibilities are split across the JS↔Rust boundary:
//! 1. **Pixel analysis** (grid detection, bar extraction) — 100% Rust, takes RGBA bytes.
//! 2. **Raw OCR** (image → text + bboxes) — Tesseract.js on the JS side.
//! 3. **OCR text parsing** (normalize, spatial-filter word list) — Rust, takes word JSON.
//!
//! This eliminates the TypeScript canvas ports entirely and removes algorithm drift.

use wasm_bindgen::prelude::*;

use crate::{
    bar_extraction::{compute_bar_alignment_score, slice_image},
    grid_detection,
    image_utils::{convert_dark_mode, remove_all_but},
    ocr::{extract_from_words, is_daily_total_page, OcrWord},
    types::{DetectionMethod, ImageType},
};

// ── Panic hook ────────────────────────────────────────────────────────────────

#[wasm_bindgen(start)]
pub fn init_panic_hook() {
    console_error_panic_hook::set_once();
}

// ── Internal helpers ──────────────────────────────────────────────────────────

/// Convert a flat RGBA byte slice to an `image::RgbImage` by dropping the alpha channel.
fn rgba_to_rgb(rgba: &[u8], width: u32, height: u32) -> Option<image::RgbImage> {
    if rgba.len() != (width * height * 4) as usize {
        return None;
    }
    let rgb: Vec<u8> = rgba
        .chunks_exact(4)
        .flat_map(|p| [p[0], p[1], p[2]])
        .collect();
    image::RgbImage::from_raw(width, height, rgb)
}

fn err_js(msg: &str) -> JsValue {
    let obj = js_sys::Object::new();
    js_sys::Reflect::set(&obj, &"error".into(), &msg.into()).unwrap();
    obj.into()
}

// ── Exported functions ────────────────────────────────────────────────────────

/// Detect the bar-chart grid region using the line-based strategy.
///
/// Input: RGBA pixel data from `ImageData.data`, image dimensions.
/// Output: JSON `{success, bounds: {upper_left_x, upper_left_y, lower_right_x, lower_right_y} | null, confidence, method, error}`
#[wasm_bindgen]
pub fn detect_grid(rgba: &[u8], width: u32, height: u32) -> JsValue {
    let Some(mut img) = rgba_to_rgb(rgba, width, height) else {
        return err_js("RGBA buffer size does not match width×height×4");
    };
    convert_dark_mode(&mut img);

    match grid_detection::detect_grid(&img, DetectionMethod::LineBased) {
        Ok(result) => serde_wasm_bindgen::to_value(&result).unwrap_or(JsValue::NULL),
        Err(e) => err_js(&e.to_string()),
    }
}

/// Extract 24 hourly bar values and compute the alignment score.
///
/// `grid_bounds_json`: serialized `GridBounds` object (output from `detect_grid`).
/// `image_type`: `"screen_time"` or `"battery"`.
///
/// Output: JSON `{hourly_values: number[], total: number, alignment_score: number}`
#[wasm_bindgen]
pub fn extract_bars(
    rgba: &[u8],
    width: u32,
    height: u32,
    grid_bounds_json: &str,
    image_type: &str,
) -> JsValue {
    let Some(mut img) = rgba_to_rgb(rgba, width, height) else {
        return err_js("RGBA buffer size does not match width×height×4");
    };
    convert_dark_mode(&mut img);

    let bounds: crate::types::GridBounds = match serde_json::from_str(grid_bounds_json) {
        Ok(b) => b,
        Err(e) => return err_js(&format!("Invalid grid_bounds_json: {e}")),
    };
    let img_type = ImageType::from_str(image_type);

    let roi_x = bounds.roi_x() as u32;
    let roi_y = bounds.roi_y() as u32;
    let roi_w = bounds.width() as u32;
    let roi_h = bounds.height() as u32;

    let hourly_row = if img_type == ImageType::Battery {
        let roi_base = image::imageops::crop_imm(&img, roi_x, roi_y, roi_w, roi_h).to_image();
        let mut roi = roi_base.clone();
        remove_all_but(&mut roi, [0, 121, 255], 30);
        let values = slice_image(&roi, 0, 0, roi_w, roi_h);
        let total: f64 = values.iter().take(24).sum();
        if total == 0.0 {
            let mut roi2 = roi_base;
            remove_all_but(&mut roi2, [255, 134, 0], 30);
            let v2 = slice_image(&roi2, 0, 0, roi_w, roi_h);
            if v2.iter().take(24).sum::<f64>() > 0.0 {
                v2
            } else {
                values
            }
        } else {
            values
        }
    } else {
        slice_image(&img, roi_x, roi_y, roi_w, roi_h)
    };

    let hourly_values: Vec<f64> = if hourly_row.len() > 24 {
        hourly_row[..24].to_vec()
    } else {
        let mut v = hourly_row.clone();
        v.resize(24, 0.0);
        v
    };

    let total: f64 = hourly_values.iter().sum();
    let roi = image::imageops::crop_imm(&img, roi_x, roi_y, roi_w, roi_h).to_image();
    let alignment_score = compute_bar_alignment_score(&roi, &hourly_values);

    serde_wasm_bindgen::to_value(&serde_json::json!({
        "hourly_values": hourly_values,
        "total": total,
        "alignment_score": alignment_score,
    }))
    .unwrap_or(JsValue::NULL)
}

/// Parse a Tesseract.js word list and extract title, total, and daily-total flag.
///
/// `words_json`: JSON array of `{text, x, y, w, h}` objects.
/// `img_width`, `img_height`: source image dimensions (needed for spatial filtering).
///
/// Output: JSON `{title, title_y, total_text, is_daily_total}`
#[wasm_bindgen]
pub fn parse_ocr_result(words_json: &str, img_width: u32, img_height: u32) -> JsValue {
    #[derive(serde::Deserialize)]
    struct WordInput {
        text: String,
        x: i32,
        y: i32,
        w: i32,
        h: i32,
    }

    let input: Vec<WordInput> = match serde_json::from_str(words_json) {
        Ok(w) => w,
        Err(e) => return err_js(&format!("Invalid words_json: {e}")),
    };

    let words: Vec<OcrWord> = input
        .into_iter()
        .map(|w| OcrWord {
            text: w.text,
            x: w.x,
            y: w.y,
            w: w.w,
            h: w.h,
        })
        .collect();

    let (title, title_y, total_text) = extract_from_words(&words, img_width, img_height);
    let texts: Vec<String> = words.iter().map(|w| w.text.clone()).collect();
    let is_daily_total = is_daily_total_page(&texts);

    serde_wasm_bindgen::to_value(&serde_json::json!({
        "title": title,
        "title_y": title_y,
        "total_text": total_text,
        "is_daily_total": is_daily_total,
    }))
    .unwrap_or(JsValue::NULL)
}

/// Normalize OCR digit confusions (I→1, O→0, S→5) in the context of time strings.
///
/// Use this on raw Tesseract.js text before display.
#[wasm_bindgen]
pub fn normalize_ocr_text(text: &str) -> String {
    crate::ocr::normalize_ocr_digits(text)
}

/// Return true when the OCR word list indicates a Daily Total / weekly summary page.
///
/// `texts_json`: JSON array of strings (one entry per OCR word).
#[wasm_bindgen]
pub fn check_is_daily_total(texts_json: &str) -> bool {
    let texts: Vec<String> = serde_json::from_str(texts_json).unwrap_or_default();
    is_daily_total_page(&texts)
}
