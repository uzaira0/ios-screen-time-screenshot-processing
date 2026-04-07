/// leptess OCR benchmark — outputs JSON lines for each image.
use leptess::{LepTess, Variable};
use serde::Serialize;
use std::{env, fs, time::Instant};

#[derive(Serialize)]
struct BBox {
    text: String,
    x: i32,
    y: i32,
    w: i32,
    h: i32,
    conf: f32,
}

#[derive(Serialize)]
struct Result {
    binding: String,
    image: String,
    psm: i32,
    text: String,
    bboxes: Vec<BBox>,
    bbox_count: usize,
    latency_ms: f64,
}

fn main() {
    let img_dir = env::args().nth(1).unwrap_or_else(|| "/images".to_string());
    let runs = 3;

    let mut entries: Vec<_> = fs::read_dir(&img_dir)
        .expect("Failed to read image dir")
        .filter_map(|e| e.ok())
        .filter(|e| {
            let name = e.file_name().to_string_lossy().to_lowercase();
            name.ends_with(".png") || name.ends_with(".jpg") || name.ends_with(".jpeg")
        })
        .collect();
    entries.sort_by_key(|e| e.file_name());

    for entry in &entries {
        let path = entry.path();
        let fname = entry.file_name().to_string_lossy().to_string();

        for psm in [3, 6] {
            let mut latencies = Vec::with_capacity(runs);
            let mut last_text = String::new();
            let mut last_bboxes: Vec<BBox> = Vec::new();

            for _ in 0..runs {
                let mut lt = match LepTess::new(None, "eng") {
                    Ok(lt) => lt,
                    Err(e) => {
                        eprintln!("Failed to init leptess: {e}");
                        continue;
                    }
                };

                let _ = lt.set_variable(Variable::TesseditPagesegMode, &psm.to_string());

                if lt.set_image(path.to_str().unwrap()).is_err() {
                    eprintln!("Failed to set image: {}", path.display());
                    continue;
                }

                let t0 = Instant::now();

                // Recognize first (required before getting boxes)
                lt.recognize();

                // Get text
                let text = lt.get_utf8_text().unwrap_or_default();

                // Get word-level bounding boxes via leptess native API
                let mut bboxes = Vec::new();
                if let Some(boxa) = lt.get_component_boxes(
                    leptess::capi::TessPageIteratorLevel_RIL_WORD,
                    true,
                ) {
                    for i in 0..boxa.get_n() {
                        if let Some(b) = boxa.get_box(i) {
                            let mut x = 0i32;
                            let mut y = 0i32;
                            let mut w = 0i32;
                            let mut h = 0i32;
                            b.get_geometry(
                                Some(&mut x), Some(&mut y),
                                Some(&mut w), Some(&mut h),
                            );
                            bboxes.push(BBox {
                                text: String::new(),
                                x, y, w, h,
                                conf: 0.0,
                            });
                        }
                    }
                }

                let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;
                latencies.push(elapsed_ms);
                last_text = text.trim().to_string();
                last_bboxes = bboxes;
            }

            if latencies.is_empty() {
                continue;
            }

            latencies.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let median = latencies[latencies.len() / 2];

            let bbox_count = last_bboxes.len();
            let result = Result {
                binding: "leptess".to_string(),
                image: fname.clone(),
                psm,
                text: last_text.clone(),
                bbox_count,
                bboxes: last_bboxes,
                latency_ms: (median * 10.0).round() / 10.0,
            };

            println!("{}", serde_json::to_string(&result).unwrap());
        }
    }
}
