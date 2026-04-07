//! Resolution lookup table for known iPhone screen dimensions.
//!
//! Port of Python line_based_detection/strategies/lookup.py.

use std::collections::HashMap;

use lazy_static::lazy_static;

/// Lookup entry: (x, y, width, height).
/// y is approximate — varies based on scroll position.
#[derive(Debug, Clone, Copy)]
pub struct LookupEntry {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

lazy_static! {
    /// Default lookup table for known iOS Screen Time screenshot resolutions.
    /// Keys are "widthxheight" resolution strings.
    pub static ref DEFAULT_LOOKUP_TABLE: HashMap<&'static str, LookupEntry> = {
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

/// Look up grid bounds for a given resolution.
pub fn lookup_resolution(width: u32, height: u32) -> Option<&'static LookupEntry> {
    let key = format!("{width}x{height}");
    DEFAULT_LOOKUP_TABLE.get(key.as_str())
}

/// Get partial bounds (x, width, height) for hints to other strategies.
pub fn get_partial_bounds(width: u32, height: u32) -> Option<(i32, i32, i32)> {
    lookup_resolution(width, height).map(|e| (e.x, e.width, e.height))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lookup_known_resolution() {
        let entry = lookup_resolution(1170, 2532);
        assert!(entry.is_some());
        let e = entry.unwrap();
        assert_eq!(e.x, 90);
        assert_eq!(e.width, 880);
        assert_eq!(e.height, 270);
    }

    #[test]
    fn test_lookup_unknown_resolution() {
        let entry = lookup_resolution(999, 999);
        assert!(entry.is_none());
    }
}
