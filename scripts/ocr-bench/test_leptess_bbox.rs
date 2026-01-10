// Quick test: verify leptess bounding boxes work
// Build: rustc test_leptess_bbox.rs -o test_bbox (needs leptess linked)
// Actually runs inside Docker

use std::env;

fn main() {
    let img_path = env::args().nth(1).unwrap_or_else(|| "/images/test.png".to_string());

    let mut lt = leptess::LepTess::new(None, "eng").expect("init");
    lt.set_image(&img_path).expect("set image");
    lt.recognize();

    // Get word-level bounding boxes
    let boxa = lt.get_component_boxes(
        leptess::capi::TessPageIteratorLevel_RIL_WORD,
        true,
    );

    match boxa {
        Some(boxes) => {
            let count = boxes.get_count();
            println!("Found {} word bounding boxes", count);
            for i in 0..count.min(10) {
                if let Some(b) = boxes.get_box_copied(i) {
                    let mut x = 0i32;
                    let mut y = 0i32;
                    let mut w = 0i32;
                    let mut h = 0i32;
                    b.get_geometry(Some(&mut x), Some(&mut y), Some(&mut w), Some(&mut h));
                    println!("  Box {}: x={} y={} w={} h={}", i, x, y, w, h);
                }
            }
        }
        None => println!("No bounding boxes returned!"),
    }
}
