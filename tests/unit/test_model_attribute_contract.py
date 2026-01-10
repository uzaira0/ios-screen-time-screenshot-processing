"""Contract test: verify all attribute accesses on SQLAlchemy models are valid.

Prevents the Flash-Processing-style bug where route code accesses
model attributes (like is_verified, is_excluded) that don't exist,
causing 500 errors that only surface at runtime.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from screenshot_processor.web.database.models import (
    Annotation,
    ConsensusResult,
    Group,
    Screenshot,
    User,
    UserQueueState,
)

# Map model names to their classes for attribute checking
MODEL_CLASSES = {
    "Screenshot": Screenshot,
    "Annotation": Annotation,
    "User": User,
    "Group": Group,
    "ConsensusResult": ConsensusResult,
    "UserQueueState": UserQueueState,
}


def _get_model_columns(model_class) -> set[str]:
    """Get all column names and relationship names for a SQLAlchemy model."""
    columns = set()
    # Mapped columns
    if hasattr(model_class, "__table__"):
        columns.update(model_class.__table__.columns.keys())
    # Relationships
    if hasattr(model_class, "__mapper__"):
        columns.update(model_class.__mapper__.relationships.keys())
    # Hybrid properties, column properties
    for name in dir(model_class):
        if not name.startswith("_"):
            columns.add(name)
    return columns


class TestExportAttributeAccess:
    """Verify the export endpoint only accesses valid Screenshot attributes."""

    def test_export_route_screenshot_attributes_exist(self):
        """Every screenshot.X access in the export code must be a real column."""
        columns = _get_model_columns(Screenshot)

        # These are the attributes accessed in the export endpoint
        # (manually maintained — if the export changes, update this list)
        export_accesses = [
            "id",
            "file_path",
            "original_filepath",
            "group_id",
            "participant_id",
            "image_type",
            "screenshot_date",
            "uploaded_at",
            "processing_status",
            "verified_by_user_ids",
            "current_annotation_count",
            "has_consensus",
            "extracted_title",
            "extracted_total",
            "extracted_hourly_data",
        ]

        missing = [attr for attr in export_accesses if attr not in columns]
        assert not missing, (
            f"Export endpoint accesses Screenshot attributes that don't exist: {missing}. "
            f"Available columns: {sorted(columns)}"
        )

    def test_consensus_result_attributes_exist(self):
        """Consensus attributes accessed in export must be real columns."""
        columns = _get_model_columns(ConsensusResult)

        consensus_accesses = [
            "disagreement_details",
            "has_consensus",
        ]

        missing = [attr for attr in consensus_accesses if attr not in columns]
        assert not missing, (
            f"Export endpoint accesses ConsensusResult attributes that don't exist: {missing}. "
            f"Available columns: {sorted(columns)}"
        )


class TestAllModelsHaveExpectedColumns:
    """Smoke test: critical columns exist on their respective models."""

    def test_screenshot_has_processing_fields(self):
        cols = _get_model_columns(Screenshot)
        for field in ["processing_status", "annotation_status", "extracted_hourly_data",
                       "extracted_title", "extracted_total", "processing_metadata"]:
            assert field in cols, f"Screenshot missing expected column: {field}"

    def test_annotation_has_hourly_values(self):
        cols = _get_model_columns(Annotation)
        assert "hourly_values" in cols
        assert "screenshot_id" in cols
        assert "user_id" in cols

    def test_user_has_auth_fields(self):
        cols = _get_model_columns(User)
        for field in ["username", "role", "is_active"]:
            assert field in cols, f"User missing expected column: {field}"
