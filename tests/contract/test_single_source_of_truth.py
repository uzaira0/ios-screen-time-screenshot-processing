"""Contract tests: verify constants are only defined in their canonical locations.

Scans source files to ensure processing constants, lookup tables, page markers,
and color values are NOT hardcoded outside of:
  1. shared/*.json (canonical)
  2. */generated_constants.* (generated)
  3. The original implementation files (legacy — must import from generated)

Run: pytest tests/contract/ -v
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
SHARED_DIR = ROOT / "shared"


def load_json(name: str) -> dict:
    with open(SHARED_DIR / f"{name}.json") as f:
        data = json.load(f)
        return {k: v for k, v in data.items() if k != "_comment"}


class TestGeneratedFilesUpToDate:
    """Verify generated constants match canonical JSON files."""

    def test_generated_constants_not_stale(self):
        """Generated files must match shared/*.json content."""
        import subprocess

        result = subprocess.run(
            ["python3", "scripts/generate-shared-constants.py", "--check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Generated constants are stale:\n{result.stdout}\n{result.stderr}"


class TestLookupTableConsistency:
    """Verify resolution lookup table is consistent across all implementations."""

    def test_all_implementations_have_same_resolutions(self):
        """All lookup tables must have the same resolution keys."""
        canonical = load_json("lookup_table")
        canonical_keys = sorted(canonical.keys())

        # Check Python
        py_file = ROOT / "src" / "screenshot_processor" / "core" / "line_based_detection" / "strategies" / "lookup.py"
        py_content = py_file.read_text()
        for res in canonical_keys:
            assert f'"{res}"' in py_content, f"Python missing resolution {res}"

        # Check TypeScript
        ts_file = ROOT / "frontend" / "src" / "core" / "implementations" / "wasm" / "processing" / "lineBasedDetection.canvas.ts"
        if ts_file.exists():
            ts_content = ts_file.read_text()
            for res in canonical_keys:
                assert f'"{res}"' in ts_content, f"TypeScript missing resolution {res}"

        # Check Rust (Tauri)
        rs_file = ROOT / "crates" / "processing" / "src" / "grid_detection" / "lookup.rs"
        rs_content = rs_file.read_text()
        for res in canonical_keys:
            assert f'"{res}"' in rs_content, f"Rust missing resolution {res}"

    def test_lookup_values_match(self):
        """All lookup tables must have identical x/width/height values."""
        canonical = load_json("lookup_table")

        # Check Rust values
        rs_file = ROOT / "crates" / "processing" / "src" / "grid_detection" / "lookup.rs"
        rs_content = rs_file.read_text()

        for res, entry in canonical.items():
            # Verify x, width, height appear near the resolution string
            pattern = re.escape(f'"{res}"')
            match = re.search(pattern + r".*?x:\s*(\d+).*?width:\s*(\d+).*?height:\s*(\d+)", rs_content, re.DOTALL)
            if match:
                assert int(match.group(1)) == entry["x"], f"Rust {res} x mismatch"
                assert int(match.group(2)) == entry["width"], f"Rust {res} width mismatch"
                assert int(match.group(3)) == entry["height"], f"Rust {res} height mismatch"


class TestPageMarkerConsistency:
    """Verify page marker words are consistent across implementations."""

    def test_daily_markers_in_rust(self):
        canonical = load_json("page_markers")
        rs_file = ROOT / "crates" / "processing" / "src" / "ocr.rs"
        rs_content = rs_file.read_text()
        for marker in canonical["daily_page_markers"]:
            assert f'"{marker}"' in rs_content, f"Rust missing daily marker: {marker}"

    def test_app_markers_in_rust(self):
        canonical = load_json("page_markers")
        rs_file = ROOT / "crates" / "processing" / "src" / "ocr.rs"
        rs_content = rs_file.read_text()
        for marker in canonical["app_page_markers"]:
            assert f'"{marker}"' in rs_content, f"Rust missing app marker: {marker}"


class TestOCRPatternConsistency:
    """Verify OCR normalization patterns produce identical results."""

    def test_normalize_test_vectors(self):
        """All normalize_ocr_digits test vectors must be in the shared JSON."""
        patterns = load_json("ocr_patterns")
        vectors = patterns.get("test_vectors", {}).get("normalize_ocr_digits", [])
        assert len(vectors) >= 10, "Need at least 10 normalization test vectors"

    def test_extract_time_test_vectors(self):
        """All extract_time_from_text test vectors must be in the shared JSON."""
        patterns = load_json("ocr_patterns")
        vectors = patterns.get("test_vectors", {}).get("extract_time_from_text", [])
        assert len(vectors) >= 10, "Need at least 10 time extraction test vectors"


class TestProcessingConstantsConsistency:
    """Verify processing constants match between implementations."""

    def test_num_slices_in_rust(self):
        canonical = load_json("processing_constants")
        rs_file = ROOT / "crates" / "processing" / "src" / "bar_extraction.rs"
        rs_content = rs_file.read_text()
        assert f"NUM_SLICES: usize = {canonical['bar_extraction']['num_slices']}" in rs_content

    def test_darken_threshold_wired_through_in_rust(self):
        """The Rust BT.601 luma threshold must come from generated_constants, not be hardcoded."""
        rs_file = ROOT / "crates" / "processing" / "src" / "image_utils.rs"
        rs_content = rs_file.read_text()
        assert "DARKEN_NON_WHITE_LUMA_THRESHOLD" in rs_content, (
            "Rust image_utils.rs must consume DARKEN_NON_WHITE_LUMA_THRESHOLD from "
            "generated_constants — do not hardcode the threshold."
        )
        assert "DARKEN_NON_WHITE_LUMA_COEFFS" in rs_content, (
            "Rust image_utils.rs must consume DARKEN_NON_WHITE_LUMA_COEFFS from generated_constants."
        )

    def test_darken_threshold_wired_through_in_python(self):
        """The Python BT.601 luma threshold must come from generated_constants, not be hardcoded."""
        py_file = ROOT / "src" / "screenshot_processor" / "core" / "image_utils.py"
        py_content = py_file.read_text()
        assert "DARKEN_NON_WHITE_LUMA_THRESHOLD" in py_content, (
            "Python image_utils.py must consume DARKEN_NON_WHITE_LUMA_THRESHOLD from "
            "generated_constants — do not hardcode the threshold."
        )

    def test_darken_threshold_value_matches_canonical(self):
        """Generated constants must carry the JSON SSoT value for the BT.601 threshold."""
        canonical = load_json("processing_constants")
        threshold = canonical["darken_non_white"]["luma_threshold"]
        for path in [
            ROOT / "crates" / "processing" / "src" / "generated_constants.rs",
            ROOT / "src" / "screenshot_processor" / "core" / "generated_constants.py",
            ROOT / "frontend" / "src" / "core" / "generated" / "constants.ts",
        ]:
            content = path.read_text()
            assert f"DARKEN_NON_WHITE_LUMA_THRESHOLD" in content, f"{path} missing threshold const"
            assert f"= {threshold}" in content, (
                f"{path} threshold value drifted from shared/processing_constants.json"
            )
