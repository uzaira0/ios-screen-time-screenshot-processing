//! Criterion benchmarks for scan_image_files.
//!
//! Parameterized benchmark groups testing directory scanning at different scales:
//! - Directory sizes: 10, 100, 1000 files
//! - File type mixes: all PNG, mixed PNG/JPEG, no images
//!
//! Run: cd frontend/src-tauri && cargo bench

use std::fs;

use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};
use tempfile::TempDir;

/// Recreate the scan_image_files logic inline for benchmarking
/// (the actual function is in lib.rs but not pub-accessible for benches)
fn scan_image_files(dir: &std::path::Path) -> Vec<(String, String)> {
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return vec![],
    };

    let mut files = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }

        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();

        if !matches!(ext.as_str(), "png" | "jpg" | "jpeg" | "heic" | "webp") {
            continue;
        }

        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown")
            .to_string();
        let path_str = path.to_string_lossy().to_string();
        files.push((name, path_str));
    }
    files
}

/// Create a temp directory with the specified number of files and mix.
fn create_test_dir(n_files: usize, mix: &str) -> TempDir {
    let dir = TempDir::new().expect("create temp dir");

    for i in 0..n_files {
        let filename = match mix {
            "all_png" => format!("image_{i:04}.png"),
            "mixed" => match i % 5 {
                0 => format!("image_{i:04}.png"),
                1 => format!("image_{i:04}.jpg"),
                2 => format!("image_{i:04}.jpeg"),
                3 => format!("image_{i:04}.webp"),
                _ => format!("image_{i:04}.heic"),
            },
            "no_images" => format!("document_{i:04}.pdf"),
            _ => format!("file_{i:04}.txt"),
        };
        fs::write(dir.path().join(filename), b"fake content").expect("write file");
    }

    dir
}

fn bench_scan_by_size(c: &mut Criterion) {
    let mut group = c.benchmark_group("scan_image_files/dir_size");

    for size in [10, 100, 1000] {
        let dir = create_test_dir(size, "all_png");
        group.bench_with_input(BenchmarkId::new("all_png", size), &size, |b, _| {
            b.iter(|| scan_image_files(dir.path()));
        });
    }

    group.finish();
}

fn bench_scan_by_mix(c: &mut Criterion) {
    let mut group = c.benchmark_group("scan_image_files/file_mix");
    let size = 100;

    for mix in ["all_png", "mixed", "no_images"] {
        let dir = create_test_dir(size, mix);
        group.bench_with_input(BenchmarkId::new(mix, size), &size, |b, _| {
            b.iter(|| scan_image_files(dir.path()));
        });
    }

    group.finish();
}

fn bench_scan_combined(c: &mut Criterion) {
    let mut group = c.benchmark_group("scan_image_files/combined");

    for size in [10, 100, 1000] {
        for mix in ["all_png", "mixed", "no_images"] {
            let dir = create_test_dir(size, mix);
            let label = format!("{mix}_{size}");
            group.bench_with_input(BenchmarkId::new(mix, size), &label, |b, _| {
                b.iter(|| scan_image_files(dir.path()));
            });
        }
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_scan_by_size,
    bench_scan_by_mix,
    bench_scan_combined
);
criterion_main!(benches);
