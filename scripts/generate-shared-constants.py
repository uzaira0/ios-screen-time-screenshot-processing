#!/usr/bin/env python3
"""Generate language-specific constants from shared/*.json canonical files.

SINGLE SOURCE OF TRUTH enforcement. Reads shared JSON files and generates:
  - Python: src/screenshot_processor/core/generated_constants.py
  - TypeScript: frontend/src/core/generated/constants.ts
  - Rust: crates/processing/src/generated_constants.rs

Usage:
    python scripts/generate-shared-constants.py          # generate all
    python scripts/generate-shared-constants.py --check  # verify generated files are up to date
"""

import json
import sys
import hashlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
SHARED_DIR = ROOT / "shared"

# Output paths
PY_OUT = ROOT / "src" / "screenshot_processor" / "core" / "generated_constants.py"
TS_OUT = ROOT / "frontend" / "src" / "core" / "generated" / "constants.ts"
RUST_OUT = ROOT / "crates" / "processing" / "src" / "generated_constants.rs"


def load_shared():
    """Load all canonical JSON files."""
    data = {}
    for f in sorted(SHARED_DIR.glob("*.json")):
        with open(f) as fh:
            raw = json.load(fh)
            # Remove _comment keys
            if isinstance(raw, dict):
                raw = {k: v for k, v in raw.items() if k != "_comment"}
            data[f.stem] = raw
    return data


def compute_hash(data: dict) -> str:
    """Compute stable hash of all shared data for staleness detection."""
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def generate_python(data: dict, hash_val: str) -> str:
    """Generate Python constants module."""
    lines = [
        '"""',
        "AUTO-GENERATED from shared/*.json — do not edit manually.",
        f"Hash: {hash_val}",
        "Regenerate: python scripts/generate-shared-constants.py",
        '"""',
        "",
        "from __future__ import annotations",
        "",
    ]

    # Lookup table
    lt = data["lookup_table"]
    lines.append("RESOLUTION_LOOKUP_TABLE: dict[str, dict[str, int]] = {")
    for res, entry in lt.items():
        lines.append(f'    "{res}": {{"x": {entry["x"]}, "y": {entry["y"]}, "width": {entry["width"]}, "height": {entry["height"]}}},')
    lines.append("}")
    lines.append("")

    # Page markers
    pm = data["page_markers"]
    lines.append(f"DAILY_PAGE_MARKERS: list[str] = {json.dumps(pm['daily_page_markers'])}")
    lines.append(f"APP_PAGE_MARKERS: list[str] = {json.dumps(pm['app_page_markers'])}")
    lines.append("")

    # Processing constants
    pc = data["processing_constants"]
    lines.append(f"NUM_SLICES: int = {pc['bar_extraction']['num_slices']}")
    lines.append(f"MAX_Y: int = {pc['bar_extraction']['max_y']}")
    lines.append(f"LOWER_GRID_BUFFER: int = {pc['bar_extraction']['lower_grid_buffer']}")
    lines.append(f"SCALE_AMOUNT: int = {pc['bar_extraction']['scale_amount']}")
    lines.append(f"DARK_MODE_THRESHOLD: int = {pc['dark_mode']['threshold']}")
    dnw = pc["darken_non_white"]
    lines.append(f"DARKEN_NON_WHITE_LUMA_THRESHOLD: int = {dnw['luma_threshold']}")
    lines.append(f"DARKEN_NON_WHITE_LUMA_COEFFS: tuple[int, int, int] = {tuple(dnw['luma_coefficients'])!r}")
    lines.append(f"DARKEN_NON_WHITE_LUMA_SHIFT: int = {dnw['luma_shift']}")
    lines.append("")
    lines.append(f"H_GRAY_MIN: int = {pc['horizontal_lines']['gray_min']}")
    lines.append(f"H_GRAY_MAX: int = {pc['horizontal_lines']['gray_max']}")
    lines.append(f"H_MIN_WIDTH_PCT: float = {pc['horizontal_lines']['min_width_pct']}")
    lines.append(f"H_MIN_LINES: int = {pc['horizontal_lines']['min_lines']}")
    lines.append(f"H_MAX_LINES: int = {pc['horizontal_lines']['max_lines']}")
    lines.append(f"H_MAX_SPACING_DEVIATION: int = {pc['horizontal_lines']['max_spacing_deviation']}")
    lines.append("")
    lines.append(f"V_GRAY_MIN: int = {pc['vertical_lines']['gray_min']}")
    lines.append(f"V_GRAY_MAX: int = {pc['vertical_lines']['gray_max']}")
    lines.append(f"V_MIN_HEIGHT_PCT: float = {pc['vertical_lines']['min_height_pct']}")
    lines.append(f"V_EXPECTED_LINES: list[int] = {json.dumps(pc['vertical_lines']['expected_lines'])}")
    lines.append(f"V_SPACING_TOLERANCE: float = {pc['vertical_lines']['spacing_tolerance']}")
    lines.append("")
    lines.append(f"EDGE_GRAY_MIN: int = {pc['grid_edge_refinement']['gray_min']}")
    lines.append(f"EDGE_GRAY_MAX: int = {pc['grid_edge_refinement']['gray_max']}")
    lines.append(f"EDGE_MIN_COVERAGE: float = {pc['grid_edge_refinement']['min_line_coverage']}")
    lines.append("")

    # Color constants
    cc = data["color_constants"]
    lines.append(f"BLUE_HUE_MIN: int = {cc['blue_hue_min']}")
    lines.append(f"BLUE_HUE_MAX: int = {cc['blue_hue_max']}")
    lines.append(f"CYAN_HUE_MIN: int = {cc['cyan_hue_min']}")
    lines.append(f"CYAN_HUE_MAX: int = {cc['cyan_hue_max']}")
    lines.append(f"COLOR_MIN_SATURATION: int = {cc['min_saturation']}")
    lines.append(f"COLOR_MIN_VALUE: int = {cc['min_value']}")
    lines.append(f"MIN_BLUE_RATIO: float = {cc['min_blue_ratio']}")
    lines.append("")

    # Test vectors
    tv = data["ocr_patterns"].get("test_vectors", {})
    if tv:
        lines.append("# OCR test vectors for cross-implementation parity testing")
        lines.append(f"OCR_NORMALIZE_TEST_VECTORS: list[tuple[str, str]] = {json.dumps(tv.get('normalize_ocr_digits', []))}")
        lines.append(f"OCR_EXTRACT_TIME_TEST_VECTORS: list[tuple[str, str]] = {json.dumps(tv.get('extract_time_from_text', []))}")
    lines.append("")

    # Export columns
    ec = data.get("export_columns", {})
    if ec:
        headers = ec["headers"]
        hourly_count = ec.get("hourly_count", 24)
        hourly_prefix = ec.get("hourly_prefix", "Hour")
        full_headers = headers + [f"{hourly_prefix} {i}" for i in range(hourly_count)]
        lines.append(f"EXPORT_CSV_HEADERS: list[str] = {json.dumps(full_headers)}")
        lines.append("")

    # Shared enums
    enums = data.get("enums", {})
    if enums:
        lines.append("# Shared enum values — single source of truth (shared/enums.json)")
        for name, values in enums.items():
            const_name = name.upper()
            lines.append(f"{const_name}: list[str] = {json.dumps(values)}")
        lines.append("")

    lines.append(f'SHARED_CONSTANTS_HASH: str = "{hash_val}"')
    lines.append("")

    return "\n".join(lines)


def generate_typescript(data: dict, hash_val: str) -> str:
    """Generate TypeScript constants module."""
    lines = [
        "/**",
        " * AUTO-GENERATED from shared/*.json — do not edit manually.",
        f" * Hash: {hash_val}",
        " * Regenerate: python scripts/generate-shared-constants.py",
        " */",
        "",
    ]

    # Lookup table
    lt = data["lookup_table"]
    lines.append("export const RESOLUTION_LOOKUP_TABLE: Record<string, { x: number; y: number; width: number; height: number }> = {")
    for res, entry in lt.items():
        lines.append(f'  "{res}": {{ x: {entry["x"]}, y: {entry["y"]}, width: {entry["width"]}, height: {entry["height"]} }},')
    lines.append("};")
    lines.append("")

    # Page markers
    pm = data["page_markers"]
    lines.append(f"export const DAILY_PAGE_MARKERS: readonly string[] = {json.dumps(pm['daily_page_markers'])} as const;")
    lines.append(f"export const APP_PAGE_MARKERS: readonly string[] = {json.dumps(pm['app_page_markers'])} as const;")
    lines.append("")

    # Processing constants
    pc = data["processing_constants"]
    lines.append(f"export const NUM_SLICES = {pc['bar_extraction']['num_slices']};")
    lines.append(f"export const MAX_Y = {pc['bar_extraction']['max_y']};")
    lines.append(f"export const LOWER_GRID_BUFFER = {pc['bar_extraction']['lower_grid_buffer']};")
    lines.append(f"export const SCALE_AMOUNT = {pc['bar_extraction']['scale_amount']};")
    lines.append(f"export const DARK_MODE_THRESHOLD = {pc['dark_mode']['threshold']};")
    dnw = pc["darken_non_white"]
    lines.append(f"export const DARKEN_NON_WHITE_LUMA_THRESHOLD = {dnw['luma_threshold']};")
    coeffs_ts = ", ".join(str(c) for c in dnw["luma_coefficients"])
    lines.append(f"export const DARKEN_NON_WHITE_LUMA_COEFFS = [{coeffs_ts}] as const;")
    lines.append(f"export const DARKEN_NON_WHITE_LUMA_SHIFT = {dnw['luma_shift']};")
    lines.append("")
    lines.append(f"export const H_GRAY_MIN = {pc['horizontal_lines']['gray_min']};")
    lines.append(f"export const H_GRAY_MAX = {pc['horizontal_lines']['gray_max']};")
    lines.append(f"export const H_MIN_WIDTH_PCT = {pc['horizontal_lines']['min_width_pct']};")
    lines.append(f"export const V_GRAY_MIN = {pc['vertical_lines']['gray_min']};")
    lines.append(f"export const V_GRAY_MAX = {pc['vertical_lines']['gray_max']};")
    lines.append(f"export const V_MIN_HEIGHT_PCT = {pc['vertical_lines']['min_height_pct']};")
    lines.append(f"export const EDGE_GRAY_MIN = {pc['grid_edge_refinement']['gray_min']};")
    lines.append(f"export const EDGE_GRAY_MAX = {pc['grid_edge_refinement']['gray_max']};")
    lines.append("")

    # Color constants
    cc = data["color_constants"]
    lines.append(f"export const BLUE_HUE_MIN = {cc['blue_hue_min']};")
    lines.append(f"export const BLUE_HUE_MAX = {cc['blue_hue_max']};")
    lines.append(f"export const CYAN_HUE_MIN = {cc['cyan_hue_min']};")
    lines.append(f"export const CYAN_HUE_MAX = {cc['cyan_hue_max']};")
    lines.append(f"export const COLOR_MIN_SATURATION = {cc['min_saturation']};")
    lines.append(f"export const COLOR_MIN_VALUE = {cc['min_value']};")
    lines.append(f"export const MIN_BLUE_RATIO = {cc['min_blue_ratio']};")
    lines.append("")

    # Export columns
    ec = data.get("export_columns", {})
    if ec:
        headers = ec["headers"]
        hourly_count = ec.get("hourly_count", 24)
        hourly_prefix = ec.get("hourly_prefix", "Hour")
        full_headers = headers + [f"{hourly_prefix} {i}" for i in range(hourly_count)]
        lines.append(f"export const EXPORT_CSV_HEADERS: readonly string[] = {json.dumps(full_headers)} as const;")
        lines.append("")

    # Shared enums
    enums = data.get("enums", {})
    if enums:
        lines.append("// Shared enum values — single source of truth (shared/enums.json)")
        for name, values in enums.items():
            const_name = name.upper()
            lines.append(f"export const {const_name} = {json.dumps(values)} as const;")
            # Also generate a union type
            type_name = "".join(word.capitalize() for word in name.split("_"))
            lines.append(f"export type {type_name} = (typeof {const_name})[number];")
            # Also generate an enum-style constant object for statuses/roles
            # Named after the enum: StageStatus, ProcessingStatus, etc.
            if name.endswith("_statuses") or name.endswith("_roles") or name.endswith("_methods"):
                # StageStatuses -> StageStatus, PhiRedactionMethods -> PhiRedactionMethod
                obj_name = type_name[:-2] if type_name.endswith("es") and not type_name.endswith("les") else type_name[:-1]
                obj_entries = ", ".join(f'{v.upper()}: "{v}" as const' for v in values)
                lines.append(f"export const {obj_name} = {{ {obj_entries} }};")
        lines.append("")

    lines.append(f'export const SHARED_CONSTANTS_HASH = "{hash_val}";')
    lines.append("")

    return "\n".join(lines)


def _rust_float(val) -> str:
    """Format a number as a Rust f64 literal (safe for both int and float input)."""
    s = str(val)
    if "." not in s:
        return s + ".0"
    return s


def generate_rust(data: dict, hash_val: str) -> str:
    """Generate Rust constants module."""
    lines = [
        "//! AUTO-GENERATED from shared/*.json — do not edit manually.",
        f"//! Hash: {hash_val}",
        "//! Regenerate: python scripts/generate-shared-constants.py",
        "",
        "use std::collections::HashMap;",
        "use lazy_static::lazy_static;",
        "",
    ]

    # Lookup table
    lt = data["lookup_table"]
    lines.append("#[derive(Debug, Clone, Copy)]")
    lines.append("pub struct LookupEntry { pub x: i32, pub y: i32, pub width: i32, pub height: i32 }")
    lines.append("")
    lines.append("lazy_static! {")
    lines.append("    pub static ref RESOLUTION_LOOKUP_TABLE: HashMap<&'static str, LookupEntry> = {")
    lines.append("        let mut m = HashMap::new();")
    for res, entry in lt.items():
        lines.append(f'        m.insert("{res}", LookupEntry {{ x: {entry["x"]}, y: {entry["y"]}, width: {entry["width"]}, height: {entry["height"]} }});')
    lines.append("        m")
    lines.append("    };")
    lines.append("}")
    lines.append("")

    # Page markers
    pm = data["page_markers"]
    daily = ", ".join(f'"{w}"' for w in pm["daily_page_markers"])
    app = ", ".join(f'"{w}"' for w in pm["app_page_markers"])
    lines.append(f"pub const DAILY_PAGE_MARKERS: &[&str] = &[{daily}];")
    lines.append(f"pub const APP_PAGE_MARKERS: &[&str] = &[{app}];")
    lines.append("")

    # Processing constants
    pc = data["processing_constants"]
    lines.append(f"pub const NUM_SLICES: usize = {pc['bar_extraction']['num_slices']};")
    lines.append(f"pub const MAX_Y: f64 = {_rust_float(pc['bar_extraction']['max_y'])};")
    lines.append(f"pub const LOWER_GRID_BUFFER: usize = {pc['bar_extraction']['lower_grid_buffer']};")
    lines.append(f"pub const DARK_MODE_THRESHOLD: f64 = {_rust_float(pc['dark_mode']['threshold'])};")
    dnw = pc["darken_non_white"]
    lines.append(f"pub const DARKEN_NON_WHITE_LUMA_THRESHOLD: u32 = {dnw['luma_threshold']};")
    coeffs_rs = ", ".join(str(c) for c in dnw["luma_coefficients"])
    lines.append(f"pub const DARKEN_NON_WHITE_LUMA_COEFFS: [u32; 3] = [{coeffs_rs}];")
    lines.append(f"pub const DARKEN_NON_WHITE_LUMA_SHIFT: u32 = {dnw['luma_shift']};")
    lines.append("")
    lines.append(f"pub const GRAY_MIN: u8 = {pc['horizontal_lines']['gray_min']};")
    lines.append(f"pub const GRAY_MAX: u8 = {pc['horizontal_lines']['gray_max']};")
    lines.append(f"pub const MIN_WIDTH_PCT: f64 = {_rust_float(pc['horizontal_lines']['min_width_pct'])};")
    lines.append(f"pub const MAX_SPACING_DEVIATION: i32 = {pc['horizontal_lines']['max_spacing_deviation']};")
    lines.append(f"pub const V_GRAY_MIN: u8 = {pc['vertical_lines']['gray_min']};")
    lines.append(f"pub const V_GRAY_MAX: u8 = {pc['vertical_lines']['gray_max']};")
    lines.append(f"pub const MIN_HEIGHT_PCT: f64 = {_rust_float(pc['vertical_lines']['min_height_pct'])};")
    lines.append(f"pub const GRID_LINE_GRAY_MIN: u8 = {pc['grid_edge_refinement']['gray_min']};")
    lines.append(f"pub const GRID_LINE_GRAY_MAX: u8 = {pc['grid_edge_refinement']['gray_max']};")
    lines.append("")

    # Color constants
    cc = data["color_constants"]
    lines.append(f"pub const BLUE_HUE_MIN: u8 = {cc['blue_hue_min']};")
    lines.append(f"pub const BLUE_HUE_MAX: u8 = {cc['blue_hue_max']};")
    lines.append(f"pub const CYAN_HUE_MIN: u8 = {cc['cyan_hue_min']};")
    lines.append(f"pub const CYAN_HUE_MAX: u8 = {cc['cyan_hue_max']};")
    lines.append(f"pub const COLOR_MIN_SATURATION: u8 = {cc['min_saturation']};")
    lines.append(f"pub const COLOR_MIN_VALUE: u8 = {cc['min_value']};")
    lines.append(f"pub const MIN_BLUE_RATIO: f64 = {_rust_float(cc['min_blue_ratio'])};")
    lines.append("")

    lines.append(f'pub const SHARED_CONSTANTS_HASH: &str = "{hash_val}";')
    lines.append("")

    return "\n".join(lines)


def main():
    check_mode = "--check" in sys.argv

    data = load_shared()
    hash_val = compute_hash(data)

    outputs = {
        PY_OUT: generate_python(data, hash_val),
        TS_OUT: generate_typescript(data, hash_val),
        RUST_OUT: generate_rust(data, hash_val),
    }

    if check_mode:
        stale = []
        for path, expected in outputs.items():
            if not path.exists():
                stale.append(f"  MISSING: {path.relative_to(ROOT)}")
            elif path.read_text() != expected:
                stale.append(f"  STALE:   {path.relative_to(ROOT)}")
        if stale:
            print("ERROR: Generated constants are out of date!")
            print("\n".join(stale))
            print(f"\nRun: python scripts/generate-shared-constants.py")
            sys.exit(1)
        else:
            print(f"All generated constants are up to date (hash: {hash_val})")
            sys.exit(0)
    else:
        for path, content in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            print(f"  Generated: {path.relative_to(ROOT)}")
        print(f"Hash: {hash_val}")


if __name__ == "__main__":
    main()
