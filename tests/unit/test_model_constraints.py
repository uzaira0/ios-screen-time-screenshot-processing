"""Tests for SQLAlchemy model constraints, types, defaults, and relationships.

These tests inspect model metadata and column definitions to catch
regressions in schema changes (nullable flags, string lengths, FK targets,
default values, enum choices) without requiring a running database.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import RelationshipProperty

from screenshot_processor.web.database.models import (
    Annotation,
    AnnotationAuditLog,
    AnnotationStatus,
    Base,
    ConsensusResult,
    Group,
    ProcessingIssue,
    ProcessingMethod,
    ProcessingStatus,
    QueueStateStatus,
    Screenshot,
    Session,
    SubmissionStatus,
    User,
    UserQueueState,
    UserRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _col(model, name: str):
    """Get a mapped column's Column object from a model class."""
    mapper = sa_inspect(model)
    return mapper.columns[name]


def _rels(model) -> dict[str, RelationshipProperty]:
    mapper = sa_inspect(model)
    return {r.key: r for r in mapper.relationships}


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestEnumValues:
    """Catch accidental renames/removals of enum members the API depends on."""

    def test_annotation_status_values(self):
        expected = {"pending", "annotated", "verified", "skipped"}
        assert {e.value for e in AnnotationStatus} == expected

    def test_processing_status_values(self):
        expected = {"pending", "processing", "completed", "failed", "skipped", "deleted"}
        assert {e.value for e in ProcessingStatus} == expected

    def test_processing_method_values(self):
        expected = {"ocr_anchored", "line_based", "manual"}
        assert {e.value for e in ProcessingMethod} == expected

    def test_user_role_values(self):
        expected = {"admin", "annotator"}
        assert {e.value for e in UserRole} == expected

    def test_submission_status_values(self):
        expected = {"submitted", "draft"}
        assert {e.value for e in SubmissionStatus} == expected

    def test_queue_state_status_values(self):
        expected = {"pending", "skipped"}
        assert {e.value for e in QueueStateStatus} == expected

    def test_enums_are_str_subclass(self):
        """Ensures enums serialize to their value in JSON contexts."""
        for enum_cls in [AnnotationStatus, ProcessingStatus, UserRole, SubmissionStatus]:
            for member in enum_cls:
                assert isinstance(member, str)


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


class TestUserModel:
    def test_tablename(self):
        assert User.__tablename__ == "users"

    def test_username_max_length(self):
        col = _col(User, "username")
        assert col.type.length == 100

    def test_username_not_nullable(self):
        assert _col(User, "username").nullable is False

    def test_username_unique(self):
        assert _col(User, "username").unique is True

    def test_email_nullable(self):
        assert _col(User, "email").nullable is True

    def test_email_max_length(self):
        assert _col(User, "email").type.length == 255

    def test_role_not_nullable(self):
        assert _col(User, "role").nullable is False

    def test_role_default(self):
        col = _col(User, "role")
        assert col.default.arg == UserRole.ANNOTATOR.value

    def test_is_active_default(self):
        col = _col(User, "is_active")
        assert col.default.arg is True

    def test_is_active_not_nullable(self):
        assert _col(User, "is_active").nullable is False

    def test_created_at_not_nullable(self):
        assert _col(User, "created_at").nullable is False

    def test_has_annotations_relationship(self):
        rels = _rels(User)
        assert "annotations" in rels
        assert rels["annotations"].mapper.class_ is Annotation

    def test_has_queue_states_relationship(self):
        rels = _rels(User)
        assert "queue_states" in rels


# ---------------------------------------------------------------------------
# Group model
# ---------------------------------------------------------------------------


class TestGroupModel:
    def test_tablename(self):
        assert Group.__tablename__ == "groups"

    def test_id_is_string_pk(self):
        col = _col(Group, "id")
        assert col.primary_key is True
        assert col.type.length == 100

    def test_name_not_nullable(self):
        assert _col(Group, "name").nullable is False

    def test_image_type_default(self):
        assert _col(Group, "image_type").default.arg == "screen_time"

    def test_has_screenshots_relationship(self):
        rels = _rels(Group)
        assert "screenshots" in rels


# ---------------------------------------------------------------------------
# Screenshot model
# ---------------------------------------------------------------------------


class TestScreenshotModel:
    def test_tablename(self):
        assert Screenshot.__tablename__ == "screenshots"

    def test_file_path_unique(self):
        assert _col(Screenshot, "file_path").unique is True

    def test_file_path_max_length(self):
        assert _col(Screenshot, "file_path").type.length == 500

    def test_file_path_not_nullable(self):
        assert _col(Screenshot, "file_path").nullable is False

    def test_annotation_status_default(self):
        col = _col(Screenshot, "annotation_status")
        assert col.default.arg is AnnotationStatus.PENDING

    def test_processing_status_default(self):
        col = _col(Screenshot, "processing_status")
        assert col.default.arg is ProcessingStatus.PENDING

    def test_target_annotations_default(self):
        assert _col(Screenshot, "target_annotations").default.arg == 1

    def test_current_annotation_count_default(self):
        assert _col(Screenshot, "current_annotation_count").default.arg == 0

    def test_has_blocking_issues_default(self):
        assert _col(Screenshot, "has_blocking_issues").default.arg is False

    def test_has_consensus_nullable(self):
        assert _col(Screenshot, "has_consensus").nullable is True

    def test_uploaded_by_fk_target(self):
        col = _col(Screenshot, "uploaded_by_id")
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "users.id"

    def test_group_id_fk_target(self):
        col = _col(Screenshot, "group_id")
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "groups.id"

    def test_resolved_by_user_id_fk(self):
        col = _col(Screenshot, "resolved_by_user_id")
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "users.id"

    def test_content_hash_nullable(self):
        assert _col(Screenshot, "content_hash").nullable is True

    def test_content_hash_length(self):
        assert _col(Screenshot, "content_hash").type.length == 128

    def test_alignment_score_nullable(self):
        assert _col(Screenshot, "alignment_score").nullable is True

    def test_has_annotations_relationship(self):
        rels = _rels(Screenshot)
        assert "annotations" in rels

    def test_has_consensus_result_relationship(self):
        rels = _rels(Screenshot)
        assert "consensus_result" in rels

    def test_has_group_relationship(self):
        rels = _rels(Screenshot)
        assert "group" in rels

    def test_extracted_hourly_data_nullable(self):
        assert _col(Screenshot, "extracted_hourly_data").nullable is True

    def test_participant_id_nullable(self):
        assert _col(Screenshot, "participant_id").nullable is True


# ---------------------------------------------------------------------------
# Annotation model
# ---------------------------------------------------------------------------


class TestAnnotationModel:
    def test_tablename(self):
        assert Annotation.__tablename__ == "annotations"

    def test_screenshot_id_fk(self):
        col = _col(Annotation, "screenshot_id")
        fks = list(col.foreign_keys)
        assert fks[0].target_fullname == "screenshots.id"

    def test_user_id_fk(self):
        col = _col(Annotation, "user_id")
        fks = list(col.foreign_keys)
        assert fks[0].target_fullname == "users.id"

    def test_hourly_values_not_nullable(self):
        assert _col(Annotation, "hourly_values").nullable is False

    def test_status_default(self):
        col = _col(Annotation, "status")
        assert col.default.arg == SubmissionStatus.SUBMITTED.value

    def test_notes_nullable(self):
        assert _col(Annotation, "notes").nullable is True

    def test_time_spent_seconds_nullable(self):
        assert _col(Annotation, "time_spent_seconds").nullable is True

    def test_unique_constraint_user_screenshot(self):
        """Each user can only have one annotation per screenshot."""
        constraints = Annotation.__table_args__
        unique_names = [c.name for c in constraints if hasattr(c, "name") and "uq_" in (c.name or "")]
        assert "uq_annotation_screenshot_user" in unique_names

    def test_has_screenshot_relationship(self):
        rels = _rels(Annotation)
        assert "screenshot" in rels

    def test_has_user_relationship(self):
        rels = _rels(Annotation)
        assert "user" in rels

    def test_has_issues_relationship(self):
        rels = _rels(Annotation)
        assert "issues" in rels


# ---------------------------------------------------------------------------
# ProcessingIssue model
# ---------------------------------------------------------------------------


class TestProcessingIssueModel:
    def test_annotation_id_fk(self):
        col = _col(ProcessingIssue, "annotation_id")
        fks = list(col.foreign_keys)
        assert fks[0].target_fullname == "annotations.id"

    def test_issue_type_max_length(self):
        assert _col(ProcessingIssue, "issue_type").type.length == 100

    def test_severity_max_length(self):
        assert _col(ProcessingIssue, "severity").type.length == 50

    def test_description_not_nullable(self):
        assert _col(ProcessingIssue, "description").nullable is False


# ---------------------------------------------------------------------------
# AnnotationAuditLog model
# ---------------------------------------------------------------------------


class TestAnnotationAuditLogModel:
    def test_tablename(self):
        assert AnnotationAuditLog.__tablename__ == "annotation_audit_logs"

    def test_annotation_fk(self):
        fks = list(_col(AnnotationAuditLog, "annotation_id").foreign_keys)
        assert fks[0].target_fullname == "annotations.id"

    def test_action_max_length(self):
        assert _col(AnnotationAuditLog, "action").type.length == 50

    def test_previous_values_nullable(self):
        assert _col(AnnotationAuditLog, "previous_values").nullable is True


# ---------------------------------------------------------------------------
# UserQueueState model
# ---------------------------------------------------------------------------


class TestUserQueueStateModel:
    def test_unique_constraint(self):
        constraints = UserQueueState.__table_args__
        unique_names = [c.name for c in constraints if hasattr(c, "name")]
        assert "uq_user_queue_state_user_screenshot" in unique_names

    def test_status_default(self):
        assert _col(UserQueueState, "status").default.arg == QueueStateStatus.PENDING.value


# ---------------------------------------------------------------------------
# ConsensusResult model
# ---------------------------------------------------------------------------


class TestConsensusResultModel:
    def test_screenshot_id_unique(self):
        assert _col(ConsensusResult, "screenshot_id").unique is True

    def test_has_consensus_not_nullable(self):
        assert _col(ConsensusResult, "has_consensus").nullable is False

    def test_disagreement_details_not_nullable(self):
        assert _col(ConsensusResult, "disagreement_details").nullable is False


# ---------------------------------------------------------------------------
# Session model
# ---------------------------------------------------------------------------


class TestSessionModel:
    def test_token_is_primary_key(self):
        assert _col(Session, "token").primary_key is True

    def test_token_length(self):
        assert _col(Session, "token").type.length == 64

    def test_username_not_nullable(self):
        assert _col(Session, "username").nullable is False

    def test_expires_at_not_nullable(self):
        assert _col(Session, "expires_at").nullable is False

    def test_last_activity_nullable(self):
        assert _col(Session, "last_activity").nullable is True


# ---------------------------------------------------------------------------
# Cross-model relationship integrity
# ---------------------------------------------------------------------------


class TestRelationshipIntegrity:
    def test_all_models_share_base(self):
        for model in [User, Group, Screenshot, Annotation, ProcessingIssue,
                       AnnotationAuditLog, UserQueueState, ConsensusResult, Session]:
            assert issubclass(model, Base)

    def test_annotation_cascade_delete_from_screenshot(self):
        rels = _rels(Screenshot)
        assert "delete-orphan" in (rels["annotations"].cascade.delete_orphan and "delete-orphan")

    def test_annotation_cascade_delete_from_user(self):
        rels = _rels(User)
        assert rels["annotations"].cascade.delete_orphan is True

    def test_consensus_result_uselist_false(self):
        """Screenshot -> ConsensusResult is one-to-one."""
        rels = _rels(Screenshot)
        assert rels["consensus_result"].uselist is False

    def test_screenshot_fk_on_delete_cascade(self):
        """Annotation.screenshot_id should CASCADE on delete."""
        col = _col(Annotation, "screenshot_id")
        fk = list(col.foreign_keys)[0]
        assert fk.ondelete == "CASCADE"

    def test_uploaded_by_fk_on_delete_set_null(self):
        col = _col(Screenshot, "uploaded_by_id")
        fk = list(col.foreign_keys)[0]
        assert fk.ondelete == "SET NULL"
