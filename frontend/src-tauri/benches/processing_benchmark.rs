//! Criterion benchmarks for the full Rust image processing pipeline.
//!
//! Metrics:
//! - grid_detect: line_based::detect on a known-resolution screenshot
//! - slice_image: slice_image on a known ROI
//! - full_pipeline: Full process_image (grid + bars + OCR)
//! - extract_line: Single extract_line call (hot in OCR-anchored)
//! - run_tesseract: Single Tesseract OCR call via leptess
//! - darken_non_white / reduce_color_count / convert_dark_mode

use criterion::{criterion_group, criterion_main, Criterion};
use image::RgbImage;
use std::path::Path;

fn load_test_image() -> Option<RgbImage> {
    let paths = [
        "/tmp/test-images/test1.png",
        "/tmp/test-images/test2.png",
    ];
    for p in &paths {
        if Path::new(p).exists() {
            if let Ok(img) = image::open(p) {
                return Some(img.to_rgb8());
            }
        }
    }
    Some(generate_synthetic_screenshot())
}

/// Generate a synthetic 896x2048 screenshot with grid-like features.
fn generate_synthetic_screenshot() -> RgbImage {
    let w = 896u32;
    let h = 2048u32;
    let mut img = RgbImage::from_fn(w, h, |_, _| image::Rgb([255, 255, 255]));

    let grid_y_positions = [673, 718, 763, 808, 853];
    let grid_x_start = 73u32;
    let grid_x_end = 763u32;

    for &y in &grid_y_positions {
        for x in grid_x_start..grid_x_end {
            if y < h && x < w {
                img.put_pixel(x, y, image::Rgb([200, 200, 200]));
            }
        }
    }

    let section_width = (grid_x_end - grid_x_start) / 4;
    for i in 1..4 {
        let x = grid_x_start + i * section_width;
        for y in 673..853 {
            if y % 3 != 0 {
                img.put_pixel(x, y, image::Rgb([200, 200, 200]));
            }
        }
    }

    let bar_height = 50u32;
    let slice_width = (grid_x_end - grid_x_start) / 24;
    for hour in [8, 12, 18] {
        let bar_x = grid_x_start + hour * slice_width + slice_width / 4;
        let bar_x_end = bar_x + slice_width / 2;
        for x in bar_x..bar_x_end.min(w) {
            for y in (853 - bar_height)..853 {
                if y < h {
                    img.put_pixel(x, y, image::Rgb([0, 0, 0]));
                }
            }
        }
    }

    img
}

fn bench_grid_detection(c: &mut Criterion) {
    let img = load_test_image().expect("Need a test image");
    let mut work = img.clone();
    ios_screen_time_image_pipeline::image_utils::convert_dark_mode(&mut work);

    c.bench_function("grid_detect_line_based", |b| {
        b.iter(|| {
            let _ = ios_screen_time_image_pipeline::grid_detection::line_based::detect(&work);
        })
    });
}

fn bench_slice_image(c: &mut Criterion) {
    let img = load_test_image().expect("Need a test image");
    let mut work = img.clone();
    ios_screen_time_image_pipeline::image_utils::convert_dark_mode(&mut work);

    let roi_x = 73u32;
    let roi_y = 673u32;
    let roi_w = 690u32;
    let roi_h = 180u32;

    c.bench_function("slice_image_24h", |b| {
        b.iter(|| {
            let _ = ios_screen_time_image_pipeline::bar_extraction::slice_image(
                &work, roi_x, roi_y, roi_w, roi_h,
            );
        })
    });
}

fn bench_full_pipeline(c: &mut Criterion) {
    let img = load_test_image().expect("Need a test image");

    c.bench_function("full_pipeline_no_ocr", |b| {
        b.iter(|| {
            let mut work = img.clone();
            ios_screen_time_image_pipeline::image_utils::convert_dark_mode(&mut work);

            let grid_result = ios_screen_time_image_pipeline::grid_detection::line_based::detect(&work);
            if let Ok(ref r) = grid_result {
                if r.success {
                    let bounds = r.bounds.unwrap();
                    let _ = ios_screen_time_image_pipeline::bar_extraction::slice_image(
                        &work,
                        bounds.roi_x() as u32,
                        bounds.roi_y() as u32,
                        bounds.width() as u32,
                        bounds.height() as u32,
                    );
                }
            }
        })
    });
}

fn bench_image_utils(c: &mut Criterion) {
    let img = load_test_image().expect("Need a test image");

    c.bench_function("darken_non_white", |b| {
        b.iter(|| {
            let mut work = img.clone();
            ios_screen_time_image_pipeline::image_utils::darken_non_white(&mut work);
        })
    });

    c.bench_function("reduce_color_count_2", |b| {
        b.iter(|| {
            let mut work = img.clone();
            ios_screen_time_image_pipeline::image_utils::reduce_color_count(&mut work, 2);
        })
    });

    c.bench_function("convert_dark_mode", |b| {
        b.iter(|| {
            let mut work = img.clone();
            ios_screen_time_image_pipeline::image_utils::convert_dark_mode(&mut work);
        })
    });
}

fn bench_extract_line(c: &mut Criterion) {
    let img = load_test_image().expect("Need a test image");
    let mut work = img.clone();
    ios_screen_time_image_pipeline::image_utils::convert_dark_mode(&mut work);

    // Bench a single extract_line call on a small region
    c.bench_function("extract_line_horiz", |b| {
        b.iter(|| {
            ios_screen_time_image_pipeline::image_utils::extract_line(
                &work, 50, 100, 650, 700, true,
            );
        })
    });

    c.bench_function("extract_line_vert", |b| {
        b.iter(|| {
            ios_screen_time_image_pipeline::image_utils::extract_line(
                &work, 50, 100, 650, 700, false,
            );
        })
    });
}

fn bench_get_pixel(c: &mut Criterion) {
    let img = load_test_image().expect("Need a test image");
    // Bench on a small subregion (what extract_line uses)
    let sub = image::imageops::crop_imm(&img, 50, 650, 50, 50).to_image();

    c.bench_function("get_pixel_small", |b| {
        b.iter(|| {
            ios_screen_time_image_pipeline::image_utils::get_pixel(&sub, -2);
        })
    });

    // Bench on a 1/3-width chunk (what prepare_image_chunks uses)
    let (w, h) = img.dimensions();
    let chunk = image::imageops::crop_imm(&img, 0, 0, w / 3, h).to_image();

    c.bench_function("get_pixel_chunk", |b| {
        b.iter(|| {
            ios_screen_time_image_pipeline::image_utils::get_pixel(&chunk, 1);
        })
    });
}

fn bench_run_tesseract(c: &mut Criterion) {
    let img = load_test_image().expect("Need a test image");
    // Small region for OCR bench (not the full image — too slow for criterion)
    let sub = image::imageops::crop_imm(&img, 0, 0, 300, 100).to_image();

    let mut group = c.benchmark_group("ocr");
    group.sample_size(10); // OCR is slow, reduce samples
    group.bench_function("run_tesseract_small", |b| {
        b.iter(|| {
            let _ = ios_screen_time_image_pipeline::ocr::run_tesseract(&sub, "3");
        })
    });
    group.finish();
}

criterion_group!(
    benches,
    bench_grid_detection,
    bench_slice_image,
    bench_full_pipeline,
    bench_image_utils,
    bench_extract_line,
    bench_get_pixel,
    bench_run_tesseract,
);
criterion_main!(benches);
