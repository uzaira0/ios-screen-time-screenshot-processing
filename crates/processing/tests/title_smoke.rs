//! Live title-extraction smoke test against the 4 real fixture images.
//!
//! The golden_pipeline snapshots only capture bar values + is_daily_total,
//! so a regression that blanks title/total_text wouldn't fail the test
//! suite. This file exercises ocr::find_title_and_total directly and
//! prints what comes back so a human (or CI log) can see the actual
//! titles. Asserts that titles are non-empty for the non-daily-total
//! pages — that's the bug we just fixed.
//!
//! Requires the `ocr` feature (default).
//!   cargo test --test title_smoke -- --nocapture

#![cfg(feature = "ocr")]

use std::path::PathBuf;

use ios_screen_time_image_pipeline::{image_utils::convert_dark_mode, ocr};

fn fixtures_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/images")
}

fn fixtures() -> Vec<(&'static str, PathBuf, bool)> {
    let dir = fixtures_dir();
    // (name, path, is_daily_total_page)
    vec![
        ("IMG_0806", dir.join("IMG_0806 Cropped.png"), true),
        ("IMG_0807", dir.join("IMG_0807 Cropped.png"), false),
        ("IMG_0808", dir.join("IMG_0808 Cropped.png"), false),
        ("IMG_0809", dir.join("IMG_0809 Cropped.png"), false),
    ]
}

#[test]
fn title_extraction_returns_non_empty_for_app_pages() {
    let mut report = Vec::new();
    let mut failures = Vec::new();

    for (name, path, is_daily) in fixtures() {
        let mut img = image::open(&path)
            .unwrap_or_else(|e| panic!("Failed to load {path:?}: {e}"))
            .to_rgb8();
        convert_dark_mode(&mut img);

        match ocr::find_title_and_total(&img) {
            Ok((title, _y, total)) => {
                report.push(format!(
                    "  {name}: is_daily={is_daily}, title={:?}, total={:?}",
                    title, total
                ));
                if is_daily {
                    if title != "Daily Total" {
                        failures.push(format!(
                            "{name}: expected title 'Daily Total' for daily-total page, got {title:?}"
                        ));
                    }
                } else if title.is_empty() {
                    failures.push(format!("{name}: title was blank for app-usage page"));
                }
            }
            Err(e) => {
                failures.push(format!("{name}: find_title_and_total errored: {e}"));
            }
        }
    }

    eprintln!("\n=== Title extraction report ===");
    for line in &report {
        eprintln!("{}", line);
    }
    eprintln!("===============================\n");

    if !failures.is_empty() {
        panic!("\n{}\n", failures.join("\n"));
    }
}
