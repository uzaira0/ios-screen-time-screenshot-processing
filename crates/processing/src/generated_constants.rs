//! AUTO-GENERATED from shared/*.json — do not edit manually.
//! Hash: 63aa46172e6b1efe
//! Regenerate: python scripts/generate-shared-constants.py

use std::collections::HashMap;
use lazy_static::lazy_static;

#[derive(Debug, Clone, Copy)]
pub struct LookupEntry { pub x: i32, pub y: i32, pub width: i32, pub height: i32 }

lazy_static! {
    pub static ref RESOLUTION_LOOKUP_TABLE: HashMap<&'static str, LookupEntry> = {
        let mut m = HashMap::new();
        m.insert("640x1136", LookupEntry { x: 30, y: 270, width: 510, height: 180 });
        m.insert("750x1334", LookupEntry { x: 60, y: 670, width: 560, height: 180 });
        m.insert("750x1624", LookupEntry { x: 60, y: 450, width: 560, height: 180 });
        m.insert("828x1792", LookupEntry { x: 70, y: 450, width: 620, height: 180 });
        m.insert("848x2266", LookupEntry { x: 70, y: 390, width: 640, height: 180 });
        m.insert("858x2160", LookupEntry { x: 70, y: 390, width: 640, height: 180 });
        m.insert("896x2048", LookupEntry { x: 70, y: 500, width: 670, height: 180 });
        m.insert("906x2160", LookupEntry { x: 70, y: 390, width: 690, height: 180 });
        m.insert("960x2079", LookupEntry { x: 80, y: 620, width: 720, height: 270 });
        m.insert("980x2160", LookupEntry { x: 80, y: 390, width: 730, height: 180 });
        m.insert("990x2160", LookupEntry { x: 80, y: 390, width: 740, height: 180 });
        m.insert("1000x2360", LookupEntry { x: 80, y: 420, width: 790, height: 180 });
        m.insert("1028x2224", LookupEntry { x: 80, y: 400, width: 820, height: 180 });
        m.insert("1028x2388", LookupEntry { x: 80, y: 400, width: 820, height: 180 });
        m.insert("1170x2532", LookupEntry { x: 90, y: 640, width: 880, height: 270 });
        m.insert("1258x2732", LookupEntry { x: 80, y: 450, width: 1020, height: 180 });
        m
    };
}

pub const DAILY_PAGE_MARKERS: &[&str] = &["WEEK", "DAY", "MOST", "USED", "CATEGORIES", "TODAY", "SHOW", "ENTERTAINMENT", "EDUCATION", "INFORMATION", "READING"];
pub const APP_PAGE_MARKERS: &[&str] = &["INFO", "DEVELOPER", "RATING", "LIMIT", "AGE", "DAILY", "AVERAGE"];

pub const NUM_SLICES: usize = 24;
pub const MAX_Y: f64 = 60.0;
pub const LOWER_GRID_BUFFER: usize = 2;
pub const DARK_MODE_THRESHOLD: f64 = 100.0;
pub const DARKEN_NON_WHITE_LUMA_THRESHOLD: u32 = 240;
pub const DARKEN_NON_WHITE_LUMA_COEFFS: [u32; 3] = [77, 150, 29];
pub const DARKEN_NON_WHITE_LUMA_SHIFT: u32 = 8;

pub const GRAY_MIN: u8 = 195;
pub const GRAY_MAX: u8 = 210;
pub const MIN_WIDTH_PCT: f64 = 0.35;
pub const MAX_SPACING_DEVIATION: i32 = 10;
pub const V_GRAY_MIN: u8 = 190;
pub const V_GRAY_MAX: u8 = 215;
pub const MIN_HEIGHT_PCT: f64 = 0.4;
pub const GRID_LINE_GRAY_MIN: u8 = 190;
pub const GRID_LINE_GRAY_MAX: u8 = 220;

pub const BLUE_HUE_MIN: u8 = 100;
pub const BLUE_HUE_MAX: u8 = 130;
pub const CYAN_HUE_MIN: u8 = 80;
pub const CYAN_HUE_MAX: u8 = 100;
pub const COLOR_MIN_SATURATION: u8 = 50;
pub const COLOR_MIN_VALUE: u8 = 50;
pub const MIN_BLUE_RATIO: f64 = 0.5;

pub const SHARED_CONSTANTS_HASH: &str = "63aa46172e6b1efe";
