"""Contract test: CSV export column schema must stay consistent.

Single source of truth: shared/export_columns.json
Generated into: Python (generated_constants.py) and TypeScript (constants.ts)
Used by: WASM client-side export, this test.

Reads the JSON SSoT directly so the test runs without installing the
screenshot_processor package — it is the contract over the SSoT, not
over any one downstream artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
EXPORT_COLUMNS_JSON = ROOT / "shared" / "export_columns.json"

_metadata_headers: list[str] = json.loads(EXPORT_COLUMNS_JSON.read_text())["headers"]
EXPORT_COLUMNS: list[str] = [*_metadata_headers, *(f"Hour {i}" for i in range(24))]


class TestExportColumnContract:
    """Verify the canonical export column set matches the SSoT."""

    def test_column_count(self):
        assert len(EXPORT_COLUMNS) == 41

    def test_hourly_columns_present(self):
        hourly = [c for c in EXPORT_COLUMNS if c.startswith("Hour ")]
        assert len(hourly) == 24
        assert hourly == [f"Hour {i}" for i in range(24)]

    def test_required_metadata_columns(self):
        required = [
            "Screenshot ID",
            "Group ID",
            "Participant ID",
            "Title",
            "OCR Total",
            "Processing Status",
            "Is Verified",
        ]
        for col in required:
            assert col in EXPORT_COLUMNS, f"Required column '{col}' missing from export"

    def test_backend_export_header_matches_contract(self):
        header_row = [
            "Screenshot ID",
            "Filename",
            "Original Filepath",
            "Group ID",
            "Participant ID",
            "Image Type",
            "Screenshot Date",
            "Uploaded At",
            "Processing Status",
            "Is Verified",
            "Verified By Count",
            "Annotation Count",
            "Has Consensus",
            "Title",
            "OCR Total",
            "Computed Total",
            "Disagreement Count",
            *[f"Hour {i}" for i in range(24)],
        ]
        assert header_row == EXPORT_COLUMNS, (
            f"Header drift from shared/export_columns.json.\n"
            f"Expected: {EXPORT_COLUMNS}\n"
            f"Got: {header_row}"
        )

    def test_no_duplicate_columns(self):
        assert len(EXPORT_COLUMNS) == len(set(EXPORT_COLUMNS))

    def test_typescript_constants_in_sync(self):
        """The generated TS constants file must contain the same header list."""
        ts_path = ROOT / "frontend" / "src" / "core" / "generated" / "constants.ts"
        if not ts_path.exists():
            return
        ts_src = ts_path.read_text()
        for col in EXPORT_COLUMNS:
            assert col in ts_src, (
                f"Header '{col}' missing from frontend/src/core/constants.ts — "
                f"regenerate via: python scripts/generate-shared-constants.py"
            )
