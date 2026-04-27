//! Emscripten WASM binary — all C-ABI exports live here so wasm-ld includes them.
//!
//! Functions defined in a `bin` are always included in the final link.
//! If they were in the `lib` rlib, wasm-ld would dead-strip them because
//! main() doesn't reference them.
//!
//! Build via: scripts/build-wasm-emscripten.sh
#![allow(unsafe_code)]
#![allow(clippy::not_unsafe_ptr_arg_deref)]

use std::{alloc, ffi::CStr, ptr, slice, sync::Once};

#[cfg(feature = "ocr")]
use ios_screen_time_image_pipeline::ocr;
use ios_screen_time_image_pipeline::{
    bar_extraction::{compute_bar_alignment_score, slice_image},
    boundary_optimizer, grid_detection,
    image_utils::{convert_dark_mode, remove_all_but},
    types::{DetectionMethod, GridBounds, ImageType},
};

// ── Internal helpers ──────────────────────────────────────────────────────────

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

fn write_json(json: &str, out: *mut u8, out_len: usize) -> i32 {
    let bytes = json.as_bytes();
    if bytes.len() + 1 > out_len {
        return -1;
    }
    unsafe {
        ptr::copy_nonoverlapping(bytes.as_ptr(), out, bytes.len());
        *out.add(bytes.len()) = 0;
    }
    bytes.len() as i32
}

fn json_err(msg: &str) -> String {
    serde_json::json!({"error": msg}).to_string()
}

fn cstr_to_str<'a>(ptr: *const u8) -> &'a str {
    if ptr.is_null() {
        return "";
    }
    unsafe { CStr::from_ptr(ptr as *const i8) }
        .to_str()
        .unwrap_or("")
}

// ── Runtime init ─────────────────────────────────────────────────────────────

// Set TESSDATA_PREFIX once so leptess finds eng.traineddata mounted at /tesseract.
// The JS loader mounts the file via mod.FS.writeFile("/tesseract/eng.traineddata").
fn ensure_tessdata_prefix() {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        unsafe { std::env::set_var("TESSDATA_PREFIX", "/tesseract") };
    });
}

// ── Memory management ─────────────────────────────────────────────────────────

#[unsafe(no_mangle)]
pub extern "C" fn pipeline_alloc(len: usize) -> *mut u8 {
    let layout = alloc::Layout::from_size_align(len.max(1), 8).unwrap();
    unsafe { alloc::alloc(layout) }
}

#[unsafe(no_mangle)]
pub extern "C" fn pipeline_free(ptr: *mut u8, len: usize) {
    if ptr.is_null() {
        return;
    }
    let layout = alloc::Layout::from_size_align(len.max(1), 8).unwrap();
    unsafe { alloc::dealloc(ptr, layout) };
}

// ── Full pipeline (OCR + grid + bars) ────────────────────────────────────────

#[unsafe(no_mangle)]
pub extern "C" fn pipeline_process(
    rgba_ptr: *const u8,
    rgba_len: usize,
    width: u32,
    height: u32,
    image_type: *const u8,
    max_shift: i32,
    grid_ul_x: i32,
    grid_ul_y: i32,
    grid_lr_x: i32,
    grid_lr_y: i32,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    ensure_tessdata_prefix();
    let rgba = unsafe { slice::from_raw_parts(rgba_ptr, rgba_len) };
    let img_type = ImageType::from_str(cstr_to_str(image_type));

    let Some(mut img) = rgba_to_rgb(rgba, width, height) else {
        return write_json(&json_err("RGBA size mismatch"), out, out_len);
    };
    convert_dark_mode(&mut img);

    // Determine grid bounds: use pre-supplied coordinates if valid,
    // else try OcrAnchored (Tesseract anchors) with LineBased as fallback.
    let (grid_success, grid_bounds_opt, grid_confidence, grid_error) =
        if grid_ul_x >= 0 && grid_ul_y >= 0 && grid_lr_x > grid_ul_x && grid_lr_y > grid_ul_y {
            (
                true,
                Some(GridBounds::new(grid_ul_x, grid_ul_y, grid_lr_x, grid_lr_y)),
                1.0_f64,
                None::<String>,
            )
        } else {
            let r = match grid_detection::detect_grid(&img, DetectionMethod::OcrAnchored) {
                Ok(r) if r.success => r,
                _ => match grid_detection::detect_grid(&img, DetectionMethod::LineBased) {
                    Ok(r) => r,
                    Err(e) => return write_json(&json_err(&format!("Grid: {e}")), out, out_len),
                },
            };
            (r.success, r.bounds, r.confidence, r.error)
        };

    // Run OCR on the FULL image. The previous header-only pre-crop was a
    // perf optimisation that diverged from the Python reference, which
    // calls pytesseract.image_to_data on the full image. Pre-cropping
    //   (a) drops daily-total page markers ("MOST USED", "CATEGORIES",
    //       "ENTERTAINMENT", "EDUCATION", "INFORMATION", "READING") that
    //       sit below the chart, so is_daily_total_page() under-counts
    //       and the title for daily-total pages comes back as a regular
    //       app name attempt instead of "Daily Total"; and
    //   (b) starves PSM 3's auto layout analysis of context, which can
    //       cause the INFO anchor word itself to be missed.
    // OCR is best-effort: failures leave title/total null but pipeline continues.
    #[cfg(feature = "ocr")]
    let (title, mut total_text, ocr_error) = match ocr::find_title_and_total(&img) {
        Ok((t, _, tot)) => (t, tot, None::<String>),
        Err(e) => (String::new(), String::new(), Some(e.to_string())),
    };
    #[cfg(not(feature = "ocr"))]
    let (title, mut total_text, ocr_error) = (String::new(), String::new(), None::<String>);
    let is_daily_total = title == "Daily Total";

    let json = if let (true, Some(mut bounds)) = (grid_success, grid_bounds_opt) {
        // Run boundary optimizer if requested and OCR total is available.
        if max_shift > 0 && !total_text.is_empty() {
            let opt = boundary_optimizer::optimize_boundaries(
                &img,
                &bounds,
                &total_text,
                max_shift,
                img_type,
            );
            bounds = opt.bounds;
            total_text = opt.corrected_total;
        }

        let roi_x = bounds.roi_x() as u32;
        let roi_y = bounds.roi_y() as u32;
        let roi_w = bounds.width() as u32;
        let roi_h = bounds.height() as u32;

        let row = if img_type == ImageType::Battery {
            let base = image::imageops::crop_imm(&img, roi_x, roi_y, roi_w, roi_h).to_image();
            let mut roi = base.clone();
            // Try orange bars first (matches canvas: [255, 121, 0] primary, [0, 134, 255] fallback)
            remove_all_but(&mut roi, [255, 121, 0], 30);
            let v = slice_image(&roi, 0, 0, roi_w, roi_h);
            if v.iter().take(24).sum::<f64>() > 0.0 {
                v
            } else {
                let mut roi2 = base;
                remove_all_but(&mut roi2, [0, 134, 255], 30);
                slice_image(&roi2, 0, 0, roi_w, roi_h)
            }
        } else {
            slice_image(&img, roi_x, roi_y, roi_w, roi_h)
        };

        let hourly: Vec<f64> = {
            let mut v = if row.len() > 24 {
                row[..24].to_vec()
            } else {
                row
            };
            v.resize(24, 0.0);
            v
        };
        let total: f64 = hourly.iter().sum();
        let roi_crop = image::imageops::crop_imm(&img, roi_x, roi_y, roi_w, roi_h).to_image();
        let alignment = compute_bar_alignment_score(&roi_crop, &hourly);

        serde_json::json!({
            "success": true,
            "hourly_values": hourly,
            "total": total,
            "alignment_score": alignment,
            "title": if title.is_empty() { serde_json::Value::Null } else { title.into() },
            "total_text": if total_text.is_empty() { serde_json::Value::Null } else { total_text.into() },
            "is_daily_total": is_daily_total,
            "grid_bounds": bounds,
            "grid_confidence": grid_confidence,
            "ocr_error": ocr_error,
        })
        .to_string()
    } else {
        serde_json::json!({
            "success": false,
            "error": grid_error.unwrap_or_default(),
            "title": if title.is_empty() { serde_json::Value::Null } else { title.into() },
            "total_text": if total_text.is_empty() { serde_json::Value::Null } else { total_text.into() },
            "is_daily_total": is_daily_total,
            "ocr_error": ocr_error,
        })
        .to_string()
    };

    write_json(&json, out, out_len)
}

/// Detect grid boundaries.
///
/// `method`: 0 = OcrAnchored with LineBased fallback (matches canvas default),
///           1 = LineBased only (fast, no OCR — use for benchmarks).
#[unsafe(no_mangle)]
pub extern "C" fn pipeline_detect_grid(
    rgba_ptr: *const u8,
    rgba_len: usize,
    width: u32,
    height: u32,
    method: i32,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    ensure_tessdata_prefix();
    let rgba = unsafe { slice::from_raw_parts(rgba_ptr, rgba_len) };

    let Some(mut img) = rgba_to_rgb(rgba, width, height) else {
        return write_json(&json_err("RGBA size mismatch"), out, out_len);
    };
    convert_dark_mode(&mut img);

    let result = if method == 1 {
        // LineBased only — no OCR, fast.
        match grid_detection::detect_grid(&img, DetectionMethod::LineBased) {
            Ok(r) => r,
            Err(e) => return write_json(&json_err(&e.to_string()), out, out_len),
        }
    } else {
        // OcrAnchored with LineBased fallback — matches canvas worker default.
        match grid_detection::detect_grid(&img, DetectionMethod::OcrAnchored) {
            Ok(r) if r.success => r,
            _ => match grid_detection::detect_grid(&img, DetectionMethod::LineBased) {
                Ok(r) => r,
                Err(e) => return write_json(&json_err(&e.to_string()), out, out_len),
            },
        }
    };

    write_json(
        &serde_json::to_string(&result).unwrap_or_else(|_| json_err("serialize failed")),
        out,
        out_len,
    )
}

/// OCR-only extraction — no grid detection, no bar extraction.
///
/// Runs Tesseract on the full image to extract title and total usage
/// text. Used by EXTRACT_TITLE and EXTRACT_TOTAL to skip grid detection
/// and bar extraction when only the OCR fields are needed.
#[unsafe(no_mangle)]
pub extern "C" fn pipeline_extract_ocr(
    rgba_ptr: *const u8,
    rgba_len: usize,
    width: u32,
    height: u32,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    ensure_tessdata_prefix();
    let rgba = unsafe { slice::from_raw_parts(rgba_ptr, rgba_len) };

    let Some(mut img) = rgba_to_rgb(rgba, width, height) else {
        return write_json(&json_err("RGBA size mismatch"), out, out_len);
    };
    convert_dark_mode(&mut img);

    // Run OCR on the FULL image to match the Python reference. See the
    // pipeline_process() function above for the rationale; the same
    // divergence applied here.
    #[cfg(feature = "ocr")]
    let (title, total_text, ocr_error) = match ocr::find_title_and_total(&img) {
        Ok((t, _, tot)) => (t, tot, None::<String>),
        Err(e) => (String::new(), String::new(), Some(e.to_string())),
    };
    #[cfg(not(feature = "ocr"))]
    let (title, total_text, ocr_error) = (String::new(), String::new(), None::<String>);
    let is_daily_total = title == "Daily Total";

    let json = serde_json::json!({
        "title": if title.is_empty() { serde_json::Value::Null } else { title.into() },
        "total_text": if total_text.is_empty() { serde_json::Value::Null } else { total_text.into() },
        "is_daily_total": is_daily_total,
        "ocr_error": ocr_error,
    })
    .to_string();

    write_json(&json, out, out_len)
}

/// Full-page OCR for PHI detection. Returns every word with bbox +
/// confidence + character offsets so the JS side can map matches back to
/// image coordinates. Replaces the Tesseract.js dependency.
#[unsafe(no_mangle)]
pub extern "C" fn pipeline_phi_words(
    rgba_ptr: *const u8,
    rgba_len: usize,
    width: u32,
    height: u32,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    ensure_tessdata_prefix();
    let rgba = unsafe { slice::from_raw_parts(rgba_ptr, rgba_len) };

    let Some(img) = rgba_to_rgb(rgba, width, height) else {
        return write_json(&json_err("RGBA size mismatch"), out, out_len);
    };

    #[cfg(feature = "ocr")]
    let json = match ocr::run_phi_ocr_words(&img) {
        Ok(phi_words) => {
            let mut full_text = String::new();
            let mut total_conf: i64 = 0;
            let mut counted = 0i64;

            let words: Vec<serde_json::Value> = phi_words
                .iter()
                .map(|w| {
                    let char_start = full_text.chars().count();
                    full_text.push_str(&w.text);
                    let char_end = full_text.chars().count();
                    full_text.push(' ');

                    if w.conf >= 0 {
                        total_conf += w.conf as i64;
                        counted += 1;
                    }

                    serde_json::json!({
                        "text": w.text,
                        "x": w.x,
                        "y": w.y,
                        "w": w.w,
                        "h": w.h,
                        "conf": w.conf,
                        "char_start": char_start,
                        "char_end": char_end,
                    })
                })
                .collect();

            let avg_conf = if counted > 0 {
                total_conf as f64 / counted as f64
            } else {
                0.0
            };

            serde_json::json!({
                "success": true,
                "words": words,
                "full_text": full_text.trim_end(),
                "avg_confidence": avg_conf,
            })
            .to_string()
        }
        Err(e) => json_err(&format!("OCR: {e}")),
    };
    #[cfg(not(feature = "ocr"))]
    let json = json_err("PHI OCR not available: ocr feature disabled");
    let _ = img; // silence unused on no-ocr builds

    write_json(&json, out, out_len)
}

fn main() {
    // Force-reference each C-ABI export so rustc doesn't dead-code-eliminate
    // them before wasm-ld sees the bin's object. emcc's --export-table /
    // EXPORTED_FUNCTIONS only works on symbols that survive the rust→object
    // link step. Without these black-boxed references, wasm-ld errors with
    // `symbol exported via --export not found: pipeline_alloc` etc.
    std::hint::black_box(pipeline_alloc as *const ());
    std::hint::black_box(pipeline_free as *const ());
    std::hint::black_box(pipeline_process as *const ());
    std::hint::black_box(pipeline_detect_grid as *const ());
    std::hint::black_box(pipeline_extract_ocr as *const ());
    std::hint::black_box(pipeline_phi_words as *const ());
}
