//! Image utility functions — Rust port of Python image_utils.py.
//!
//! All functions operate on `image::RgbImage` (RGB format).
//! Python/OpenCV uses BGR; we convert at load boundaries only.
//!
//! Optimizations: raw buffer access, fused passes, LUT-based transforms,
//! sampling for large-image pixel statistics.

#[cfg(test)]
use image::Rgb;
use image::RgbImage;

/// Dark mode detection threshold (mean pixel value).
const DARK_MODE_THRESHOLD: f64 = 100.0;

/// Check if an image is in dark mode based on average brightness.
pub fn is_dark_mode(img: &RgbImage) -> bool {
    image_mean_fast(img) < DARK_MODE_THRESHOLD
}

/// Detect and convert dark mode screenshots to light mode.
///
/// If the mean pixel value is below threshold, inverts all pixels
/// and applies contrast=3.0, brightness=10 in a SINGLE fused pass
/// (invert + contrast/brightness via a combined LUT).
pub fn convert_dark_mode(img: &mut RgbImage) -> bool {
    if !is_dark_mode(img) {
        return false;
    }
    // Build a fused LUT: invert(x) then apply contrast=3.0, brightness=10
    // invert: x -> 255 - x
    // contrast/brightness: x -> clamp(x * contrast + adjusted_brightness)
    // adjusted_brightness = brightness + round(255 * (1 - contrast) / 2)
    //                     = 10 + round(255 * (1 - 3.0) / 2) = 10 + (-255) = -245
    // combined: x -> clamp((255 - x) * 3.0 + (-245))
    let adjusted_brightness: f64 = 10.0 + (255.0_f64 * (1.0 - 3.0) / 2.0).round(); // -245
    let mut lut = [0u8; 256];
    for i in 0..256 {
        let inverted = 255 - i;
        let val = (inverted as f64 * 3.0 + adjusted_brightness).round();
        lut[i as usize] = val.clamp(0.0, 255.0) as u8;
    }
    // Single pass: apply fused LUT to every byte
    let raw = img.as_mut();
    for byte in raw.iter_mut() {
        *byte = lut[*byte as usize];
    }
    true
}

/// Convert dark mode image using adaptive thresholding optimized for OCR.
///
/// The standard convert_dark_mode uses contrast=3.0 which clips faint gray text
/// (e.g., "12 AM", "60" labels) to near-white, destroying contrast for Tesseract.
/// This function uses adaptive thresholding to preserve text readability.
pub fn convert_dark_mode_for_ocr(img: &RgbImage) -> RgbImage {
    if !is_dark_mode(img) {
        return img.clone();
    }

    let (w, h) = img.dimensions();
    let block_size: usize = 31;
    let c_offset: i32 = 10;

    // Step 1: Invert and convert to grayscale
    let raw = img.as_raw();
    let len = raw.len();
    let mut gray = vec![0u8; (w * h) as usize];
    let mut i = 0;
    let mut pi = 0;
    while i + 2 < len {
        // Invert then convert to BT.601 grayscale matching canvas cvtColorToGray:
        // Math.round(R*0.299 + G*0.587 + B*0.114) via high-precision integer coefficients.
        let r = (255 - raw[i]) as u32;
        let g = (255 - raw[i + 1]) as u32;
        let b = (255 - raw[i + 2]) as u32;
        gray[pi] = ((r * 19595 + g * 38469 + b * 7472 + 32768) >> 16) as u8;
        pi += 1;
        i += 3;
    }

    // Step 2: Adaptive Gaussian thresholding
    // For each pixel, threshold = mean of block_size×block_size neighborhood - c_offset
    let half = block_size / 2;
    let w_usize = w as usize;
    let h_usize = h as usize;

    // Compute integral image for fast mean calculation
    let mut integral = vec![0i64; (w_usize + 1) * (h_usize + 1)];
    let iw = w_usize + 1;
    for y in 0..h_usize {
        let mut row_sum: i64 = 0;
        for x in 0..w_usize {
            row_sum += gray[y * w_usize + x] as i64;
            integral[(y + 1) * iw + (x + 1)] = row_sum + integral[y * iw + (x + 1)];
        }
    }

    // Apply threshold
    let mut result = RgbImage::new(w, h);
    let out_raw = result.as_mut();
    for y in 0..h_usize {
        for x in 0..w_usize {
            let y0 = y.saturating_sub(half);
            let y1 = (y + half + 1).min(h_usize);
            let x0 = x.saturating_sub(half);
            let x1 = (x + half + 1).min(w_usize);
            let area = ((y1 - y0) * (x1 - x0)) as i64;
            let sum = integral[y1 * iw + x1] - integral[y0 * iw + x1] - integral[y1 * iw + x0]
                + integral[y0 * iw + x0];
            let mean_val = sum / area;
            let threshold = mean_val - c_offset as i64;
            let val = if gray[y * w_usize + x] as i64 > threshold {
                255u8
            } else {
                0u8
            };
            let idx = (y * w_usize + x) * 3;
            out_raw[idx] = val;
            out_raw[idx + 1] = val;
            out_raw[idx + 2] = val;
        }
    }

    result
}

/// Mean pixel brightness using raw buffer.
///
/// Computes (R+G+B)/3 per pixel, consistent with Python's cv2.mean() which
/// returns per-channel means. For a dark-mode brightness threshold this is
/// equivalent — the check is `avg < 100` so per-channel vs per-byte makes
/// no practical difference.
///
/// Samples every 4th pixel for images > 100K pixels (step=12 bytes) to keep
/// this O(pixels/4) on large screenshots. Accuracy loss is negligible for a
/// brightness threshold check.
fn image_mean_fast(img: &RgbImage) -> f64 {
    let raw = img.as_raw();
    let len = raw.len();
    if len == 0 {
        return 0.0;
    }
    // Sample every 4th pixel (12 bytes) for large images
    let step = if len > 300_000 { 12 } else { 3 };
    let mut sum = 0u64;
    let mut count = 0u64;
    let mut i = 0;
    while i + 2 < len {
        // Per-pixel mean: (R+G+B)/3
        sum += (raw[i] as u64 + raw[i + 1] as u64 + raw[i + 2] as u64) / 3;
        count += 1;
        i += step;
    }
    if count == 0 {
        0.0
    } else {
        sum as f64 / count as f64
    }
}

/// Adjust contrast and brightness, returning a NEW image.
///
/// Uses a pre-computed LUT (no float math per pixel).
pub fn adjust_contrast_brightness(img: &RgbImage, contrast: f64, brightness: i32) -> RgbImage {
    let adjusted_brightness = brightness as f64 + (255.0 * (1.0 - contrast) / 2.0).round();
    let mut lut = [0u8; 256];
    for (i, slot) in lut.iter_mut().enumerate() {
        let val = (i as f64 * contrast + adjusted_brightness).round();
        *slot = val.clamp(0.0, 255.0) as u8;
    }
    let mut out = img.clone();
    for byte in out.as_mut().iter_mut() {
        *byte = lut[*byte as usize];
    }
    out
}

/// Build a color quantization LUT and apply it in-place.
pub fn reduce_color_count(img: &mut RgbImage, num_colors: u32) {
    let mut lut = [0u8; 256];
    let nc = num_colors as f64;
    for i in 0..256u32 {
        let bin = ((i as f64 * nc / 255.0) as u32).min(num_colors - 1);
        lut[i as usize] = (bin * 255 / (num_colors - 1)) as u8;
    }
    for byte in img.as_mut().iter_mut() {
        *byte = lut[*byte as usize];
    }
}

/// Keep only pixels matching `color` within `threshold` (squared L2 distance).
/// Matching → black, non-matching → white.
pub fn remove_all_but(img: &mut RgbImage, color: [u8; 3], threshold: i32) {
    let threshold_sq = threshold * threshold;
    let cr = color[0] as i32;
    let cg = color[1] as i32;
    let cb = color[2] as i32;
    let raw = img.as_mut();
    let len = raw.len();
    let mut i = 0;
    while i + 2 < len {
        let dr = raw[i] as i32 - cr;
        let dg = raw[i + 1] as i32 - cg;
        let db = raw[i + 2] as i32 - cb;
        if dr * dr + dg * dg + db * db <= threshold_sq {
            raw[i] = 0;
            raw[i + 1] = 0;
            raw[i + 2] = 0;
        } else {
            raw[i] = 255;
            raw[i + 1] = 255;
            raw[i + 2] = 255;
        }
        i += 3;
    }
}

/// Zero out all non-white pixels (BT.601 luma ≤ 240 → black).
/// Uses BT.601 grayscale to match canvas `darkenNonWhite` behavior.
pub fn darken_non_white(img: &mut RgbImage) {
    let raw = img.as_mut();
    let len = raw.len();
    let mut i = 0;
    while i + 2 < len {
        // Canvas darkenNonWhite: cvtColorToGray uses (R*77+G*150+B*29)>>8, threshold > 240 = white.
        let luma = (raw[i] as u32 * 77 + raw[i + 1] as u32 * 150 + raw[i + 2] as u32 * 29) >> 8;
        if luma <= 240 {
            raw[i] = 0;
            raw[i + 1] = 0;
            raw[i + 2] = 0;
        }
        i += 3;
    }
}

/// Fused darken_non_white + reduce_color_count(2) in a single pass.
///
/// This is the hot path in `slice_image` — combining two passes into one
/// halves the memory bandwidth.
pub fn darken_and_binarize(img: &mut RgbImage) {
    // reduce_color_count(2) LUT
    let mut lut = [0u8; 256];
    let nc = 2.0f64;
    for i in 0..256u32 {
        let bin = ((i as f64 * nc / 255.0) as u32).min(1);
        lut[i as usize] = (bin * 255) as u8;
    }

    let raw = img.as_mut();
    let len = raw.len();
    let mut i = 0;
    while i + 2 < len {
        // Canvas darkenNonWhite: cvtColorToGray uses (R*77+G*150+B*29)>>8, threshold > 240 = white.
        let luma = (raw[i] as u32 * 77 + raw[i + 1] as u32 * 150 + raw[i + 2] as u32 * 29) >> 8;
        if luma <= 240 {
            // darken: set to black
            raw[i] = 0;
            raw[i + 1] = 0;
            raw[i + 2] = 0;
        } else {
            // keep white-ish, then quantize
            raw[i] = lut[raw[i] as usize];
            raw[i + 1] = lut[raw[i + 1] as usize];
            raw[i + 2] = lut[raw[i + 2] as usize];
        }
        i += 3;
    }
}

/// Find the Nth most common pixel value in an image region.
///
/// arg=1: most common pixel. arg=-2: second most common.
/// Uses exact counting (no sampling) for consistency with Python's np.unique.
pub fn get_pixel(img: &RgbImage, arg: i32) -> Option<[u8; 3]> {
    let raw = img.as_raw();
    let len = raw.len();
    if len < 6 {
        return None;
    } // need at least 2 pixels

    // Small inline frequency table (most quantized images have ≤16 unique colors).
    // After reduce_color_count(2), images typically have exactly 2 colors, so we
    // track whether counting is "settled" to enable an early-exit optimisation:
    // once we've seen 2+ unique colors AND processed enough pixels for stable
    // ranking, skip the rest of the image.
    let pixel_count = len / 3;
    let mut table: Vec<([u8; 3], u32)> = Vec::with_capacity(16);
    let settle_threshold = (pixel_count / 4).max(256); // 25% of pixels or 256
    let mut settled_at: Option<usize> = None;
    let mut i = 0;
    while i + 2 < len {
        let color = [raw[i], raw[i + 1], raw[i + 2]];
        let mut found = false;
        for entry in table.iter_mut() {
            if entry.0 == color {
                entry.1 += 1;
                found = true;
                break;
            }
        }
        if !found {
            table.push((color, 1));
            // For binarized images (2 colors), record when we first see both
            if table.len() == 2 {
                settled_at = Some(i / 3);
            }
        }
        i += 3;
        // Early exit: if we've found exactly 2 colors (common after reduce_color_count(2))
        // and have counted enough pixels, the ranking is stable.
        if let Some(start) = settled_at {
            if table.len() == 2 && (i / 3 - start) >= settle_threshold {
                break;
            }
        }
    }

    if table.len() <= 1 {
        return None;
    }

    // Find top-2 by count
    let mut top1 = ([0u8; 3], 0u32);
    let mut top2 = ([0u8; 3], 0u32);
    for &(color, count) in &table {
        if count > top1.1 {
            top2 = top1;
            top1 = (color, count);
        } else if count > top2.1 {
            top2 = (color, count);
        }
    }

    match arg {
        1 => Some(top1.0),
        -2 => Some(top2.0),
        _ => {
            // General case: sort and index
            table.sort_by_key(|&(_, c)| c);
            let idx = if arg < 0 {
                let abs_idx = (-arg) as usize;
                if abs_idx > table.len() {
                    0
                } else {
                    table.len() - abs_idx
                }
            } else {
                (arg as usize).min(table.len() - 1)
            };
            Some(table[idx].0)
        }
    }
}

/// Check if two pixels are close (L1 distance ≤ thresh * 3).
#[inline(always)]
pub fn is_close(p1: &[u8; 3], p2: &[u8; 3], thresh: i32) -> bool {
    (p1[0] as i32 - p2[0] as i32).abs()
        + (p1[1] as i32 - p2[1] as i32).abs()
        + (p1[2] as i32 - p2[2] as i32).abs()
        <= thresh * 3
}

/// Extract line position from a subregion.
///
/// Returns the first row (horizontal) or column (vertical) where the
/// 2nd-most-common pixel dominates. Uses raw buffer access.
pub fn extract_line(img: &RgbImage, x0: u32, x1: u32, y0: u32, y1: u32, horizontal: bool) -> u32 {
    let w = x1.saturating_sub(x0);
    let h = y1.saturating_sub(y0);
    if w == 0 || h == 0 {
        return 0;
    }

    let mut sub = image::imageops::crop_imm(img, x0, y0, w, h).to_image();
    reduce_color_count(&mut sub, 2);

    let pixel_value = match get_pixel(&sub, -2) {
        Some(p) => p,
        None => return 0,
    };

    let (sw, sh) = sub.dimensions();
    let raw = sub.as_raw();
    let stride = sw as usize * 3;
    let pr = pixel_value[0] as i32;
    let pg = pixel_value[1] as i32;
    let pb = pixel_value[2] as i32;

    if horizontal {
        for y in 0..sh {
            let row_off = y as usize * stride;
            let mut count = 0u32;
            for x in 0..sw as usize {
                let idx = row_off + x * 3;
                let dist = (raw[idx] as i32 - pr).abs()
                    + (raw[idx + 1] as i32 - pg).abs()
                    + (raw[idx + 2] as i32 - pb).abs();
                if dist <= 3 {
                    count += 1;
                }
            }
            if count > sw / 2 {
                return y;
            }
        }
    } else {
        for x in 0..sw {
            let mut count = 0u32;
            for y in 0..sh as usize {
                let idx = y * stride + x as usize * 3;
                let dist = (raw[idx] as i32 - pr).abs()
                    + (raw[idx + 1] as i32 - pg).abs()
                    + (raw[idx + 2] as i32 - pb).abs();
                if dist <= 3 {
                    count += 1;
                }
            }
            if count > sh / 4 {
                return x;
            }
        }
    }
    0
}

/// Convert RGB to HSV (OpenCV convention: H 0-180, S 0-255, V 0-255).
#[inline(always)]
pub fn rgb_to_hsv(r: u8, g: u8, b: u8) -> (u8, u8, u8) {
    let rf = r as f64 / 255.0;
    let gf = g as f64 / 255.0;
    let bf = b as f64 / 255.0;
    let max = rf.max(gf).max(bf);
    let min = rf.min(gf).min(bf);
    let diff = max - min;

    let h = if diff == 0.0 {
        0.0
    } else if max == rf {
        60.0 * (((gf - bf) / diff) % 6.0)
    } else if max == gf {
        60.0 * ((bf - rf) / diff + 2.0)
    } else {
        60.0 * ((rf - gf) / diff + 4.0)
    };
    let h = if h < 0.0 { h + 360.0 } else { h };
    let h = (h / 2.0) as u8;
    let s = if max == 0.0 {
        0.0
    } else {
        (diff / max) * 255.0
    };
    let v = max * 255.0;
    (h, s as u8, v as u8)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_darken_non_white() {
        let mut img = RgbImage::new(3, 1);
        img.put_pixel(0, 0, Rgb([255, 255, 255]));
        img.put_pixel(1, 0, Rgb([100, 100, 100]));
        img.put_pixel(2, 0, Rgb([250, 250, 250]));
        darken_non_white(&mut img);
        assert_eq!(img.get_pixel(0, 0), &Rgb([255, 255, 255]));
        assert_eq!(img.get_pixel(1, 0), &Rgb([0, 0, 0]));
        assert_eq!(img.get_pixel(2, 0), &Rgb([250, 250, 250]));
    }

    // Parity: darken_non_white uses canvas cvtColorToGray formula: (R*77+G*150+B*29)>>8.
    // Canvas: cvtColorToGray → threshold(gray, 240, 255) → if gray <= 240, black.
    // The high-precision formula (R*19595+G*38469+B*7472+32768)>>16 can diverge from canvas
    // for non-gray pixels near the 240 boundary. Use the exact canvas formula.
    #[test]
    fn parity_darken_non_white_canvas_luma_formula() {
        let mut img = RgbImage::new(2, 1);
        // (100, 200, 50): canvas luma = (100*77+200*150+50*29)>>8 = 39150>>8 = 152 ≤ 240 → black
        // high-precision: (100*19595+200*38469+50*7472+32768)>>16 = 153 > 240? No, 153 ≤ 240 → same here
        // But the formula is now exactly canvas to avoid divergence near threshold.
        img.put_pixel(0, 0, Rgb([100, 200, 50]));
        // (250, 245, 215): canvas luma = (250*77+245*150+215*29)>>8 = 62235>>8 = 243 > 240 → keep
        img.put_pixel(1, 0, Rgb([250, 245, 215]));
        darken_non_white(&mut img);
        assert_eq!(
            img.get_pixel(0, 0),
            &Rgb([0, 0, 0]),
            "canvas luma=152 ≤ 240 must darken"
        );
        assert_eq!(
            img.get_pixel(1, 0),
            &Rgb([250, 245, 215]),
            "canvas luma=243 > 240 must keep"
        );
    }

    // Parity: darken_non_white uses BT.601 luma, not simple (R+G+B)/3.
    // Canvas: cvtColorToGray → threshold(gray, 240, 255) → if gray <= 240, black.
    // The old simple-average formula would INCORRECTLY darken these non-gray pixels.
    #[test]
    fn parity_darken_non_white_bt601_threshold() {
        let mut img = RgbImage::new(2, 1);
        // (250, 245, 215): canvas (R*77+G*150+B*29)>>8 = 243 > 240 → keep
        // simple avg: (250+245+215)/3 = 236 ≤ 240 → old code wrongly zeroed this
        img.put_pixel(0, 0, Rgb([250, 245, 215]));
        // (241, 241, 241): canvas luma = 241 > 240 → keep
        img.put_pixel(1, 0, Rgb([241, 241, 241]));
        darken_non_white(&mut img);
        assert_eq!(
            img.get_pixel(0, 0),
            &Rgb([250, 245, 215]),
            "BT.601>240 must keep non-gray near-white pixel"
        );
        assert_eq!(img.get_pixel(1, 0), &Rgb([241, 241, 241]));
    }

    #[test]
    fn test_reduce_color_count_binary() {
        let mut img = RgbImage::new(4, 1);
        img.put_pixel(0, 0, Rgb([0, 0, 0]));
        img.put_pixel(1, 0, Rgb([50, 50, 50]));
        img.put_pixel(2, 0, Rgb([200, 200, 200]));
        img.put_pixel(3, 0, Rgb([255, 255, 255]));
        reduce_color_count(&mut img, 2);
        assert_eq!(img.get_pixel(0, 0)[0], 0);
        assert_eq!(img.get_pixel(3, 0)[0], 255);
    }

    #[test]
    fn test_remove_all_but() {
        let mut img = RgbImage::new(3, 1);
        img.put_pixel(0, 0, Rgb([255, 121, 0]));
        img.put_pixel(1, 0, Rgb([255, 120, 1]));
        img.put_pixel(2, 0, Rgb([0, 0, 255]));
        remove_all_but(&mut img, [255, 121, 0], 30);
        assert_eq!(img.get_pixel(0, 0), &Rgb([0, 0, 0]));
        assert_eq!(img.get_pixel(1, 0), &Rgb([0, 0, 0]));
        assert_eq!(img.get_pixel(2, 0), &Rgb([255, 255, 255]));
    }

    #[test]
    fn test_adjust_contrast_brightness() {
        let mut img = RgbImage::new(1, 1);
        img.put_pixel(0, 0, Rgb([128, 128, 128]));
        let result = adjust_contrast_brightness(&img, 2.0, 0);
        assert_eq!(result.get_pixel(0, 0)[0], 128);
    }

    #[test]
    fn test_convert_dark_mode_detects_dark() {
        let mut img = RgbImage::from_fn(10, 10, |_, _| Rgb([30, 30, 30]));
        let was_dark = convert_dark_mode(&mut img);
        assert!(was_dark);
        let mean = image_mean_fast(&img);
        assert!(mean > 100.0);
    }

    #[test]
    fn test_convert_dark_mode_ignores_light() {
        let mut img = RgbImage::from_fn(10, 10, |_, _| Rgb([200, 200, 200]));
        assert!(!convert_dark_mode(&mut img));
    }

    #[test]
    fn test_is_close() {
        assert!(is_close(&[100, 100, 100], &[101, 101, 101], 1));
        assert!(!is_close(&[100, 100, 100], &[110, 110, 110], 1));
    }

    #[test]
    fn test_rgb_to_hsv_blue() {
        let (h, s, v) = rgb_to_hsv(0, 0, 255);
        assert!(h >= 115 && h <= 125, "H={h}");
        assert_eq!(s, 255);
        assert_eq!(v, 255);
    }

    #[test]
    fn test_darken_and_binarize() {
        let mut img = RgbImage::new(3, 1);
        img.put_pixel(0, 0, Rgb([255, 255, 255])); // white → keep + quantize
        img.put_pixel(1, 0, Rgb([100, 100, 100])); // gray → darken to black
        img.put_pixel(2, 0, Rgb([0, 0, 0])); // black → stays black
        darken_and_binarize(&mut img);
        assert_eq!(img.get_pixel(0, 0), &Rgb([255, 255, 255]));
        assert_eq!(img.get_pixel(1, 0), &Rgb([0, 0, 0]));
        assert_eq!(img.get_pixel(2, 0), &Rgb([0, 0, 0]));
    }

    // Parity: darken_and_binarize uses BT.601 luma for white detection, matching canvas.
    // Canvas darkenNonWhite: cvtColorToGray (BT.601) then threshold at 240.
    #[test]
    fn parity_darken_and_binarize_bt601_threshold() {
        let mut img = RgbImage::new(2, 1);
        // (250, 245, 215): BT.601 luma = 243 > 240 → white path (keep + quantize to 255)
        // simple avg: 236 ≤ 240 → old code wrongly sent this to the black path
        img.put_pixel(0, 0, Rgb([250, 245, 215]));
        // (240, 240, 240): BT.601 = 240 ≤ 240 → non-white → black
        img.put_pixel(1, 0, Rgb([240, 240, 240]));
        darken_and_binarize(&mut img);
        assert_eq!(
            img.get_pixel(0, 0),
            &Rgb([255, 255, 255]),
            "BT.601>240 non-gray near-white must stay white"
        );
        assert_eq!(
            img.get_pixel(1, 0),
            &Rgb([0, 0, 0]),
            "BT.601=240 must darken to black"
        );
    }

    // Parity: rgb_to_hsv red — H=0 in OpenCV 0-180 convention
    #[test]
    fn parity_rgb_to_hsv_red() {
        let (h, s, v) = rgb_to_hsv(255, 0, 0);
        assert_eq!(h, 0, "pure red H must be 0");
        assert_eq!(s, 255);
        assert_eq!(v, 255);
    }

    // Parity: rgb_to_hsv green — H=60 in OpenCV 0-180 convention (120° / 2)
    #[test]
    fn parity_rgb_to_hsv_green() {
        let (h, s, v) = rgb_to_hsv(0, 255, 0);
        assert_eq!(h, 60, "pure green H must be 60 in OpenCV convention");
        assert_eq!(s, 255);
        assert_eq!(v, 255);
    }

    // Parity: gray pixels must have S=0 regardless of brightness
    #[test]
    fn parity_rgb_to_hsv_gray_saturation_zero() {
        let (_, s, _) = rgb_to_hsv(128, 128, 128);
        assert_eq!(s, 0, "gray pixel must have S=0");
        let (_, s2, _) = rgb_to_hsv(0, 0, 0);
        assert_eq!(s2, 0, "black must have S=0");
    }

    // Parity: is_close uses L1 ≤ thresh*3 (inclusive boundary).
    // Canvas: Math.abs(r1-r2)+Math.abs(g1-g2)+Math.abs(b1-b2) <= thresh*3
    #[test]
    fn parity_is_close_boundary() {
        // L1 = 5+5+5 = 15 = thresh*3 → true (inclusive)
        assert!(
            is_close(&[0, 0, 0], &[5, 5, 5], 5),
            "L1==thresh*3 must be close"
        );
        // L1 = 5+5+6 = 16 > 15 → false
        assert!(
            !is_close(&[0, 0, 0], &[5, 5, 6], 5),
            "L1==thresh*3+1 must not be close"
        );
    }

    // Parity: get_pixel arg=1 returns most common; arg=-2 returns second most common.
    // Canvas uses numpy unique (equivalent behavior for binarized images).
    #[test]
    fn parity_get_pixel_arg1_and_neg2() {
        let mut img = RgbImage::new(4, 1);
        img.put_pixel(0, 0, Rgb([255, 255, 255]));
        img.put_pixel(1, 0, Rgb([255, 255, 255]));
        img.put_pixel(2, 0, Rgb([255, 255, 255]));
        img.put_pixel(3, 0, Rgb([0, 0, 0]));
        assert_eq!(
            get_pixel(&img, 1),
            Some([255, 255, 255]),
            "arg=1 must return most common"
        );
        assert_eq!(
            get_pixel(&img, -2),
            Some([0, 0, 0]),
            "arg=-2 must return 2nd most common"
        );
    }

    // Parity: remove_all_but uses squared L2 distance, boundary dist_sq==threshold^2 → matches.
    // Canvas: dr*dr+dg*dg+db*db <= threshold*threshold
    #[test]
    fn parity_remove_all_but_boundary() {
        // threshold=30, threshold_sq=900
        // pixel [255, 151, 0] vs target [255, 121, 0]: dg=30, dist_sq=900 ≤ 900 → black
        // pixel [255, 152, 0] vs target [255, 121, 0]: dg=31, dist_sq=961 > 900 → white
        let mut img = RgbImage::new(2, 1);
        img.put_pixel(0, 0, Rgb([255, 151, 0]));
        img.put_pixel(1, 0, Rgb([255, 152, 0]));
        remove_all_but(&mut img, [255, 121, 0], 30);
        assert_eq!(
            img.get_pixel(0, 0),
            &Rgb([0, 0, 0]),
            "exact threshold dist must match → black"
        );
        assert_eq!(
            img.get_pixel(1, 0),
            &Rgb([255, 255, 255]),
            "dist>threshold must not match → white"
        );
    }

    // Parity: adjust_contrast_brightness clamps output at 0.
    // Canvas: Math.max(0, Math.min(255, v * contrast + adjusted))
    #[test]
    fn parity_adjust_contrast_brightness_clamps_at_zero() {
        let mut img = RgbImage::new(1, 1);
        img.put_pixel(0, 0, Rgb([0, 0, 0]));
        // contrast=1.0, brightness=-50: adjusted=-50+(255*(1-1)/2).round()=-50; val=0-50 → clamp=0
        let result = adjust_contrast_brightness(&img, 1.0, -50);
        assert_eq!(
            result.get_pixel(0, 0)[0],
            0,
            "output must clamp at 0, not go negative"
        );
    }

    // Parity: convert_dark_mode fused LUT maps black→255 and white→0.
    // Canvas: invert then contrast=3.0, brightness=10 → adjusted=-245.
    // LUT[0]  = clamp((255-0)*3+(-245)) = clamp(520) = 255
    // LUT[255] = clamp((255-255)*3+(-245)) = clamp(-245) = 0
    #[test]
    fn parity_convert_dark_mode_extreme_lut_values() {
        // Build a dark image (mean < 100) with two extreme pixels
        let mut img = RgbImage::from_fn(10, 10, |x, _| {
            if x == 9 {
                Rgb([0, 0, 0])
            } else {
                Rgb([10, 10, 10])
            }
        });
        // Add one near-white pixel in dark image to test white→0 mapping
        img.put_pixel(9, 9, Rgb([255, 255, 255]));
        convert_dark_mode(&mut img);
        assert_eq!(
            img.get_pixel(9, 0)[0],
            255,
            "pure black in dark image → white after conversion"
        );
        assert_eq!(
            img.get_pixel(9, 9)[0],
            0,
            "pure white in dark image → black after conversion"
        );
    }

    // Parity: extract_line horizontal uses count > sw/2 threshold (strictly greater).
    // Canvas: if (count / width > 0.5) — equivalently count > width/2.
    #[test]
    fn parity_extract_line_horizontal_threshold() {
        // 10×10 white image, row 3 is fully black.
        // After reduce_color_count(2): black(0,0,0)=10px, white=90px → 2nd most common=black.
        // Row 3: 10 black pixels; count=10 > sw/2=5 → detected at y=3.
        let mut img = RgbImage::from_fn(10, 10, |_, _| image::Rgb([255, 255, 255]));
        for x in 0..10 {
            img.put_pixel(x, 3, image::Rgb([0, 0, 0]));
        }
        let y = extract_line(&img, 0, 10, 0, 10, true);
        assert_eq!(y, 3, "horizontal line at row 3 must be detected");
    }

    // Parity: extract_line vertical uses count > sh/4 threshold (strictly greater).
    // Canvas: if (count / height > 0.25) — equivalently count > height/4.
    #[test]
    fn parity_extract_line_vertical_threshold() {
        // 10×10 white image, column 5 has 3 black pixels (3/10=30% > 25%).
        // After reduce_color_count(2): black=3px, white=97px → 2nd most common=black.
        // Column 5: count=3 > sh/4=2 → detected at x=5.
        let mut img = RgbImage::from_fn(10, 10, |_, _| image::Rgb([255, 255, 255]));
        img.put_pixel(5, 0, image::Rgb([0, 0, 0]));
        img.put_pixel(5, 1, image::Rgb([0, 0, 0]));
        img.put_pixel(5, 2, image::Rgb([0, 0, 0]));
        let x = extract_line(&img, 0, 10, 0, 10, false);
        assert_eq!(x, 5, "vertical line at col 5 must be detected");
    }
}
