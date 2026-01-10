/// tesseract-rs OCR benchmark — outputs JSON lines for each image.
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
        let path_str = path.to_str().unwrap();

        for psm in [3i32, 6] {
            let mut latencies = Vec::with_capacity(runs);
            let mut last_text = String::new();

            for _ in 0..runs {
                let t0 = Instant::now();

                // tesseract-rs: simple text extraction
                let result = tesseract::ocr(path_str, "eng");
                let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;

                match result {
                    Ok(text) => {
                        latencies.push(elapsed_ms);
                        last_text = text.trim().to_string();
                    }
                    Err(e) => {
                        eprintln!("tesseract-rs error on {fname}: {e}");
                    }
                }
            }

            if latencies.is_empty() {
                continue;
            }

            latencies.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let median = latencies[latencies.len() / 2];

            // tesseract-rs doesn't support bounding boxes directly
            let result = Result {
                binding: "tesseract_rs".to_string(),
                image: fname.clone(),
                psm,
                text: last_text.clone(),
                bboxes: vec![],
                bbox_count: 0,
                latency_ms: (median * 10.0).round() / 10.0,
            };

            println!("{}", serde_json::to_string(&result).unwrap());
        }
    }
}
