//! End-to-end golden regression tests.
//!
//! Runs every processing stage on all 4 real fixture images and compares
//! output byte-for-byte against stored JSON snapshots.
//!
//! Generate / update snapshots:
//!   UPDATE_GOLDEN=1 cargo test --test golden_pipeline --no-default-features
//!
//! Run regression check (CI):
//!   cargo test --test golden_pipeline --no-default-features

use std::{fs, path::PathBuf};

use image::RgbImage;
use ios_screen_time_image_pipeline::{
    bar_extraction::{compute_bar_alignment_score, slice_image},
    grid_detection::detect_grid,
    image_utils::convert_dark_mode,
    process_image,
    types::{DetectionMethod, GridBounds, ImageType},
};
use serde::Serialize;

// ── path helpers ──────────────────────────────────────────────────────────────

fn fixtures_dir() -> PathBuf {
    // CARGO_MANIFEST_DIR = crates/processing; fixtures are two levels up.
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/images")
}

fn snapshots_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/snapshots")
}

fn update_golden() -> bool {
    std::env::var("UPDATE_GOLDEN").is_ok()
}

fn fixture_images() -> Vec<(&'static str, PathBuf)> {
    let dir = fixtures_dir();
    vec![
        ("IMG_0806", dir.join("IMG_0806 Cropped.png")),
        ("IMG_0807", dir.join("IMG_0807 Cropped.png")),
        ("IMG_0808", dir.join("IMG_0808 Cropped.png")),
        ("IMG_0809", dir.join("IMG_0809 Cropped.png")),
    ]
}

fn load_and_convert(path: &PathBuf) -> (RgbImage, bool) {
    let mut img = image::open(path)
        .unwrap_or_else(|e| panic!("Failed to load {path:?}: {e}"))
        .to_rgb8();
    let was_dark = convert_dark_mode(&mut img);
    (img, was_dark)
}

// ── pixel diagnostics ─────────────────────────────────────────────────────────

/// FNV-1a hash over all pixel bytes — deterministic, order-sensitive.
fn pixel_hash(img: &RgbImage) -> u64 {
    const OFFSET: u64 = 0xcbf29ce484222325;
    const PRIME: u64 = 0x100000001b3;
    let mut h = OFFSET;
    for &byte in img.as_raw() {
        h ^= byte as u64;
        h = h.wrapping_mul(PRIME);
    }
    h
}

/// Per-channel sums for diagnostic failure messages.
fn channel_sums(img: &RgbImage) -> [u64; 3] {
    let mut sums = [0u64; 3];
    for px in img.pixels() {
        sums[0] += px[0] as u64;
        sums[1] += px[1] as u64;
        sums[2] += px[2] as u64;
    }
    sums
}

// ── golden file assertion ─────────────────────────────────────────────────────

fn assert_golden<T: Serialize>(name: &str, value: &T) {
    let dir = snapshots_dir();
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join(format!("{name}.json"));
    let actual = serde_json::to_string_pretty(value).unwrap();

    if update_golden() {
        fs::write(&path, &actual)
            .unwrap_or_else(|e| panic!("Failed to write golden file {path:?}: {e}"));
        return;
    }

    let stored = fs::read_to_string(&path).unwrap_or_else(|_| {
        panic!(
            "Golden file not found: {path:?}\n\
             Run with UPDATE_GOLDEN=1 to generate snapshots."
        )
    });

    if stored.trim() != actual.trim() {
        // Write the actual output for diffing
        let fail_dir =
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../target/golden-failures");
        let _ = fs::create_dir_all(&fail_dir);
        let _ = fs::write(fail_dir.join(format!("{name}.actual.json")), &actual);

        panic!(
            "Golden mismatch for snapshot '{name}'\n\
             Expected (stored):\n{stored}\n\
             Actual:\n{actual}\n\
             Actual written to: target/golden-failures/{name}.actual.json"
        );
    }
}

// ── snapshot types ────────────────────────────────────────────────────────────

#[derive(Serialize)]
struct DarkModeSnapshot {
    was_dark_mode: bool,
    width: u32,
    height: u32,
    /// FNV-1a hash of all pixel bytes (hex string avoids JSON u64 precision concerns).
    pixel_hash: String,
    channel_sums: [u64; 3],
}

#[derive(Serialize)]
struct GridSnapshot {
    success: bool,
    bounds: Option<GridBounds>,
    /// Confidence rounded to 4 decimal places for stable JSON representation.
    confidence: f64,
    method: String,
    error: Option<String>,
}

#[derive(Serialize)]
struct BarExtractionSnapshot {
    /// Whether grid detection succeeded (false → hourly_values will be empty).
    grid_success: bool,
    /// Raw slice_image output: 24 hourly values + total (25 elements total).
    slice_image_output: Vec<f64>,
    /// Sum of first 24 hourly values.
    total: f64,
    /// Bar alignment score from compute_bar_alignment_score, rounded to 6dp.
    alignment_score: f64,
}

#[derive(Serialize)]
struct PipelineSnapshot {
    /// false when grid detection or pipeline itself fails.
    success: bool,
    hourly_values: Option<Vec<f64>>,
    total: f64,
    alignment_score: Option<f64>,
    grid_bounds: Option<GridBounds>,
    detection_method: String,
    is_daily_total: bool,
}

// ── helpers for rounding floats in snapshots ──────────────────────────────────

fn round6(v: f64) -> f64 {
    (v * 1_000_000.0).round() / 1_000_000.0
}

fn round4(v: f64) -> f64 {
    (v * 10_000.0).round() / 10_000.0
}

// ── stage 1: dark mode conversion ─────────────────────────────────────────────

#[test]
fn golden_dark_mode_conversion() {
    for (name, path) in fixture_images() {
        let (img, was_dark) = load_and_convert(&path);
        let snap = DarkModeSnapshot {
            was_dark_mode: was_dark,
            width: img.width(),
            height: img.height(),
            pixel_hash: format!("{:016x}", pixel_hash(&img)),
            channel_sums: channel_sums(&img),
        };
        assert_golden(&format!("{name}_dark_mode"), &snap);
    }
}

// ── stage 2: line-based grid detection ────────────────────────────────────────

#[test]
fn golden_line_based_grid_detection() {
    for (name, path) in fixture_images() {
        let (img, _) = load_and_convert(&path);
        let result = detect_grid(&img, DetectionMethod::LineBased)
            .unwrap_or_else(|e| panic!("Grid detection error for {name}: {e}"));
        let snap = GridSnapshot {
            success: result.success,
            bounds: result.bounds,
            confidence: round4(result.confidence),
            method: result.method,
            error: result.error,
        };
        assert_golden(&format!("{name}_grid"), &snap);
    }
}

// ── stage 3: bar extraction + alignment score ─────────────────────────────────

#[test]
fn golden_bar_extraction() {
    for (name, path) in fixture_images() {
        let (img, _) = load_and_convert(&path);
        let grid_result = detect_grid(&img, DetectionMethod::LineBased)
            .unwrap_or_else(|e| panic!("Grid detection error for {name}: {e}"));

        let snap = if grid_result.success {
            let bounds = grid_result.bounds.unwrap();
            let roi_x = bounds.roi_x() as u32;
            let roi_y = bounds.roi_y() as u32;
            let roi_w = bounds.width() as u32;
            let roi_h = bounds.height() as u32;

            // slice_image returns 25 elements: 24 hourly + 1 total
            let raw = slice_image(&img, roi_x, roi_y, roi_w, roi_h);
            let hourly_24: Vec<f64> = raw.iter().take(24).copied().collect();
            let total: f64 = hourly_24.iter().sum();

            // alignment score uses the non-binarized ROI
            let roi_original =
                image::imageops::crop_imm(&img, roi_x, roi_y, roi_w, roi_h).to_image();
            let alignment_score = compute_bar_alignment_score(&roi_original, &hourly_24);

            BarExtractionSnapshot {
                grid_success: true,
                slice_image_output: raw,
                total,
                alignment_score: round6(alignment_score),
            }
        } else {
            BarExtractionSnapshot {
                grid_success: false,
                slice_image_output: vec![],
                total: 0.0,
                alignment_score: 0.0,
            }
        };
        assert_golden(&format!("{name}_bar_extraction"), &snap);
    }
}

// ── stage 4: full pipeline (process_image) ───────────────────────────────────
//
// Calls process_image — the real top-level entry point — which internally runs
// load → dark-mode → grid detection → bar extraction → alignment score.
// No manual grid coordinates are supplied; detection is entirely automatic.
//
// Snapshot suffix is config-specific:
//   no-default-features → {name}_pipeline.json
//   default (OCR)       → {name}_pipeline_ocr.json
//
// `is_daily_total` legitimately differs between configs: without OCR it is
// always false; with OCR Tesseract reads the title and sets it correctly.
// Core processing fields (hourly_values, total, alignment_score, grid_bounds)
// must be byte-identical across both configs.

#[test]
fn golden_full_pipeline() {
    #[cfg(feature = "ocr")]
    let suffix = "pipeline_ocr";
    #[cfg(not(feature = "ocr"))]
    let suffix = "pipeline";

    for (name, path) in fixture_images() {
        let path_str = path.to_str().unwrap();
        let snap = match process_image(path_str, ImageType::ScreenTime, DetectionMethod::LineBased)
        {
            Ok(r) => PipelineSnapshot {
                success: true,
                hourly_values: r.hourly_values,
                total: r.total,
                alignment_score: r.alignment_score.map(round6),
                grid_bounds: r.grid_bounds,
                detection_method: r.detection_method,
                is_daily_total: r.is_daily_total,
            },
            Err(e) => PipelineSnapshot {
                success: false,
                hourly_values: None,
                total: 0.0,
                alignment_score: None,
                grid_bounds: None,
                detection_method: format!("error: {e}"),
                is_daily_total: false,
            },
        };
        assert_golden(&format!("{name}_{suffix}"), &snap);
    }
}
