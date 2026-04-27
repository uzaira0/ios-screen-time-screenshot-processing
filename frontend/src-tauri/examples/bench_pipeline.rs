//! Benchmark pipeline: process images and output results.
//!
//! Usage:
//!   cargo run --release --example bench_pipeline -- /path/to/images     # human-readable
//!   cargo run --release --example bench_pipeline -- --jsonl /path/to/images  # JSONL output
//!   cat paths.txt | cargo run --release --example bench_pipeline -- --jsonl --stdin

use std::{
    env, fs,
    io::{self, BufRead},
    time::Instant,
};

use serde_json::json;

fn main() {
    let args: Vec<String> = env::args().collect();
    let jsonl = args.iter().any(|a| a == "--jsonl");
    let stdin_mode = args.iter().any(|a| a == "--stdin");

    let paths: Vec<String> = if stdin_mode {
        io::stdin()
            .lock()
            .lines()
            .filter_map(|l| l.ok())
            .filter(|l| !l.is_empty())
            .collect()
    } else {
        let dir = args
            .iter()
            .find(|a| !a.starts_with('-') && a.as_str() != args[0].as_str())
            .map(|s| s.as_str())
            .unwrap_or("/tmp/test-images");
        fs::read_dir(dir)
            .expect("Failed to read directory")
            .filter_map(|e| e.ok())
            .filter(|e| {
                e.path()
                    .extension()
                    .map(|ext| matches!(ext.to_str(), Some("png" | "jpg" | "jpeg")))
                    .unwrap_or(false)
            })
            .map(|e| e.path().to_string_lossy().into_owned())
            .collect()
    };

    if !jsonl {
        println!("Processing {} images", paths.len());
        println!(
            "{:<50} {:>10} {:>10} {:>8} {:>8}",
            "Image", "Method", "Time(ms)", "Total", "Score"
        );
        println!("{}", "-".repeat(90));
    }

    let mut total_time_ms = 0u64;
    let mut processed = 0u32;

    for path in &paths {
        let name = std::path::Path::new(path)
            .file_name()
            .unwrap_or_default()
            .to_string_lossy();
        let start = Instant::now();

        let img = match image::open(path) {
            Ok(i) => i.to_rgb8(),
            Err(e) => {
                if jsonl {
                    println!(
                        "{}",
                        json!({"path": path, "ok": false, "err": format!("{e}")})
                    );
                } else {
                    println!("{name:<50} ERROR: {e}");
                }
                continue;
            }
        };

        let (w, h) = img.dimensions();
        let mut work = img.clone();
        ios_screen_time_image_pipeline::image_utils::convert_dark_mode(&mut work);

        let grid_result = ios_screen_time_image_pipeline::grid_detection::line_based::detect(&work);

        match grid_result {
            Ok(ref r) if r.success => {
                let bounds = r.bounds.unwrap();
                let row = ios_screen_time_image_pipeline::bar_extraction::slice_image(
                    &work,
                    bounds.roi_x() as u32,
                    bounds.roi_y() as u32,
                    bounds.width() as u32,
                    bounds.height() as u32,
                );

                let roi = image::imageops::crop_imm(
                    &work,
                    bounds.roi_x() as u32,
                    bounds.roi_y() as u32,
                    bounds.width() as u32,
                    bounds.height() as u32,
                )
                .to_image();
                let score =
                    ios_screen_time_image_pipeline::bar_extraction::compute_bar_alignment_score(
                        &roi,
                        &row[..24],
                    );

                let total: f64 = row[..24].iter().sum();
                let elapsed = start.elapsed().as_millis() as u64;
                total_time_ms += elapsed;
                processed += 1;

                if jsonl {
                    let hourly_str: String = row[..24]
                        .iter()
                        .map(|v| format!("{v:.1}"))
                        .collect::<Vec<_>>()
                        .join(",");
                    println!(
                        "{}",
                        json!({
                            "path": path,
                            "ok": true,
                            "bounds": format!("{},{},{},{}", bounds.roi_x(), bounds.roi_y(), bounds.width(), bounds.height()),
                            "hourly": hourly_str,
                            "total": (total * 10.0).round() / 10.0,
                            "score": (score * 100.0).round() / 100.0,
                            "ms": elapsed,
                        })
                    );
                } else {
                    println!(
                        "{name:<50} {res:<10} {elapsed:>7}ms {total:>8.1} {score:>7.2}",
                        res = format!("{w}x{h}")
                    );
                    let vals: Vec<String> = row[..24].iter().map(|v| format!("{v:.1}")).collect();
                    println!("  hours: [{}]", vals.join(", "));
                }
            }
            Ok(ref r) => {
                let elapsed = start.elapsed().as_millis();
                if jsonl {
                    println!(
                        "{}",
                        json!({"path": path, "ok": false, "err": r.error.as_deref().unwrap_or("unknown"), "ms": elapsed})
                    );
                } else {
                    println!(
                        "{name:<50} {res:<10} {elapsed:>7}ms GRID_FAIL: {}",
                        r.error.as_deref().unwrap_or("unknown"),
                        res = format!("{w}x{h}")
                    );
                }
            }
            Err(e) => {
                let elapsed = start.elapsed().as_millis();
                if jsonl {
                    println!(
                        "{}",
                        json!({"path": path, "ok": false, "err": format!("{e}"), "ms": elapsed})
                    );
                } else {
                    println!("{name:<50} ERROR: {e}");
                }
            }
        }
    }

    if !jsonl && processed > 0 {
        println!("{}", "-".repeat(90));
        println!(
            "Processed {processed}/{} images. Total: {total_time_ms}ms, Avg: {}ms/image",
            paths.len(),
            total_time_ms / processed as u64
        );
    }
}
