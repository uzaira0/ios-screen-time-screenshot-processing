"""
Snapshot test for the OpenAPI schema.

Catches accidental schema drift by comparing the current OpenAPI spec
against a stored snapshot. If the snapshot doesn't exist, it creates one.
If it differs, the test fails with instructions to update the snapshot.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).parent.parent / "fixtures" / "openapi_schema_snapshot.json"


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """Ensure required env vars are set before importing the app."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-at-least-32-chars-long-for-testing")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    # Clear SITE_PASSWORD so tests don't require it
    monkeypatch.delenv("SITE_PASSWORD", raising=False)


def _normalize_schema(schema: dict) -> dict:
    """Remove volatile fields that change between runs (e.g., version)."""
    normalized = json.loads(json.dumps(schema, sort_keys=True))
    # Remove version info since it may change without schema changes
    info = normalized.get("info", {})
    info.pop("version", None)
    return normalized


def test_openapi_schema_snapshot():
    """Compare current OpenAPI schema against stored snapshot."""
    # Import inside test so env vars are already set via fixture
    from screenshot_processor.web.config import reset_settings

    reset_settings()

    from screenshot_processor.web.api.main import app

    schema = app.openapi()
    normalized = _normalize_schema(schema)

    if not SNAPSHOT_PATH.exists():
        # First run: create the snapshot
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
        pytest.skip(
            f"OpenAPI schema snapshot created at {SNAPSHOT_PATH}. "
            "Re-run tests to verify."
        )

    stored = json.loads(SNAPSHOT_PATH.read_text())

    if normalized != stored:
        # Write the current schema to a temp file for easy diffing
        actual_path = SNAPSHOT_PATH.with_suffix(".actual.json")
        actual_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")

        # Find specific differences for a helpful message
        diff_keys = _find_diff_keys(stored, normalized)
        diff_summary = ", ".join(diff_keys[:10])
        if len(diff_keys) > 10:
            diff_summary += f" ... and {len(diff_keys) - 10} more"

        pytest.fail(
            f"OpenAPI schema has changed! Differences found in: {diff_summary}\n"
            f"Current schema written to: {actual_path}\n"
            f"To update the snapshot, run:\n"
            f"  cp {actual_path} {SNAPSHOT_PATH}\n"
            f"Or delete {SNAPSHOT_PATH} and re-run tests."
        )


def _find_diff_keys(expected: dict, actual: dict, prefix: str = "") -> list[str]:
    """Recursively find keys that differ between two dicts."""
    diffs = []
    all_keys = set(list(expected.keys()) + list(actual.keys()))
    for key in sorted(all_keys):
        path = f"{prefix}.{key}" if prefix else key
        if key not in expected:
            diffs.append(f"+{path}")
        elif key not in actual:
            diffs.append(f"-{path}")
        elif isinstance(expected[key], dict) and isinstance(actual[key], dict):
            diffs.extend(_find_diff_keys(expected[key], actual[key], path))
        elif expected[key] != actual[key]:
            diffs.append(path)
    return diffs
