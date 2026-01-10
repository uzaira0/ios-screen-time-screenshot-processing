# Database Behavior Specification

This document specifies the expected behavior of the screenshot annotator database, including cascade deletions, foreign key relationships, and constraint enforcement.

## Entity Relationship Overview

```
User (1) ─────< Annotation (N)
  │               │
  │               └──< ProcessingIssue (N)
  │               │
  │               └──< AnnotationAuditLog (N)
  │
  └─────< UserQueueState (N)
  │
  └── uploaded_by ──> Screenshot (SET NULL)

Group (1) ───── group_id ──> Screenshot (SET NULL)

Screenshot (1) ─────< Annotation (N) ───── CASCADE
  │
  └─────< ConsensusResult (1) ───── CASCADE
  │
  └─────< UserQueueState (N) ───── CASCADE
```

## Deletion Behaviors

### When a Screenshot is Deleted

| Related Entity | Behavior | Rationale |
|----------------|----------|-----------|
| `Annotation` | **CASCADE DELETE** | Annotations are meaningless without their screenshot |
| `ConsensusResult` | **CASCADE DELETE** | Consensus is for a specific screenshot |
| `UserQueueState` | **CASCADE DELETE** | Queue state tracks screenshot progress |
| `ProcessingIssue` | **CASCADE DELETE** (via Annotation) | Issues are tied to specific annotations |
| `AnnotationAuditLog` | **CASCADE DELETE** (via Annotation) | Logs reference deleted annotations |

**Expected Outcome**: Deleting a screenshot removes ALL related annotations, consensus results, queue states, processing issues, and audit logs. No orphaned entries should remain.

### When a User is Deleted

| Related Entity | Behavior | Rationale |
|----------------|----------|-----------|
| `Annotation` | **CASCADE DELETE** | User's annotations are removed with them |
| `UserQueueState` | **CASCADE DELETE** | User's queue state is removed |
| `Screenshot.uploaded_by_id` | **SET NULL** | Screenshots remain; uploader reference is cleared |
| `Screenshot.resolved_by_user_id` | **SET NULL** | Resolution history preserved, resolver cleared |
| `AnnotationAuditLog.user_id` | **SET NULL** | Audit trail preserved, user reference cleared |

**Expected Outcome**: Deleting a user removes their annotations and queue states but preserves screenshots they uploaded (with `uploaded_by_id = NULL`).

### When a Group is Deleted

| Related Entity | Behavior | Rationale |
|----------------|----------|-----------|
| `Screenshot.group_id` | **SET NULL** | Screenshots can exist without a group |

**Expected Outcome**: Deleting a group does NOT delete its screenshots. Screenshots remain with `group_id = NULL`. This is intentional to prevent accidental data loss.

**Important**: To delete a group AND its screenshots, use the admin endpoint `DELETE /api/v1/admin/groups/{group_id}` which explicitly deletes screenshots first.

### When an Annotation is Deleted

| Related Entity | Behavior | Rationale |
|----------------|----------|-----------|
| `ProcessingIssue` | **CASCADE DELETE** | Issues are tied to specific annotations |
| `AnnotationAuditLog` | **CASCADE DELETE** | Audit logs reference the annotation |

## Unique Constraints

| Table | Constraint | Columns | Purpose |
|-------|------------|---------|---------|
| `users` | `ix_users_username` | `username` | One account per username |
| `users` | `ix_users_email` | `email` | One account per email |
| `screenshots` | `file_path` | `file_path` | No duplicate file paths |
| `annotations` | `uq_annotation_screenshot_user` | `(screenshot_id, user_id)` | One annotation per user per screenshot |
| `user_queue_states` | `uq_user_queue_state_user_screenshot` | `(user_id, screenshot_id)` | One queue state per user per screenshot |
| `consensus_results` | `ix_consensus_results_screenshot_id` | `screenshot_id` | One consensus per screenshot |

## NOT NULL Constraints

Critical non-nullable fields:

| Table | Column | Rationale |
|-------|--------|-----------|
| `users.username` | User identification required |
| `screenshots.file_path` | Must know where image is stored |
| `screenshots.image_type` | Processing depends on type |
| `annotations.screenshot_id` | Must reference a screenshot |
| `annotations.user_id` | Must know who annotated |
| `annotations.hourly_values` | Core annotation data |
| `consensus_results.screenshot_id` | Must reference a screenshot |
| `consensus_results.has_consensus` | Core consensus flag |
| `consensus_results.disagreement_details` | Always store analysis |

## Foreign Key Relationships

### CASCADE Deletions

```sql
-- annotations.screenshot_id -> screenshots.id ON DELETE CASCADE
-- annotations.user_id -> users.id ON DELETE CASCADE
-- consensus_results.screenshot_id -> screenshots.id ON DELETE CASCADE
-- user_queue_states.screenshot_id -> screenshots.id ON DELETE CASCADE
-- user_queue_states.user_id -> users.id ON DELETE CASCADE
-- processing_issues.annotation_id -> annotations.id ON DELETE CASCADE
-- annotation_audit_logs.annotation_id -> annotations.id ON DELETE CASCADE
```

### SET NULL Deletions

```sql
-- screenshots.uploaded_by_id -> users.id ON DELETE SET NULL
-- screenshots.resolved_by_user_id -> users.id ON DELETE SET NULL
-- screenshots.group_id -> groups.id ON DELETE SET NULL
-- annotation_audit_logs.screenshot_id -> screenshots.id ON DELETE SET NULL
-- annotation_audit_logs.user_id -> users.id ON DELETE SET NULL
```

## Admin Cleanup Endpoints

### Check for Orphaned Entries

```bash
curl -s "http://localhost:8002/api/v1/admin/orphaned-entries" -H "X-Username: admin"
```

Response:
```json
{
  "orphaned_annotations": 0,
  "orphaned_consensus": 0,
  "orphaned_queue_states": 0,
  "screenshots_without_group": 0
}
```

### Clean Up Orphaned Entries

```bash
curl -s -X POST "http://localhost:8002/api/v1/admin/cleanup-orphaned" -H "X-Username: admin"
```

Response:
```json
{
  "success": true,
  "deleted_annotations": 0,
  "deleted_consensus": 0,
  "deleted_queue_states": 0,
  "message": "Cleaned up 0 orphaned entries"
}
```

## Testing

All cascade behaviors and constraints are tested in:
```
tests/integration/test_database_constraints.py
```

Run the tests:
```bash
pytest tests/integration/test_database_constraints.py -v
```

### Test Database Limitations

The integration tests use SQLite (in-memory) for speed. SQLite has limitations:

1. **Foreign key constraints are NOT enforced by default** (`PRAGMA foreign_keys=OFF`)
2. **CASCADE and SET NULL behaviors** are only tested via SQLAlchemy ORM relationships, not DB-level constraints

Tests that require DB-level enforcement are marked as skipped with clear documentation.
The production PostgreSQL database fully enforces all constraints.

### Cascade Behavior Types

| Type | Enforcement Level | Works in SQLite Tests |
|------|-------------------|----------------------|
| ORM Cascade (`cascade="all, delete-orphan"`) | SQLAlchemy | Yes |
| DB Cascade (`ondelete="CASCADE"`) | PostgreSQL | No (skipped) |
| DB SET NULL (`ondelete="SET NULL"`) | PostgreSQL | No (skipped) |

Most critical cascades use ORM-level enforcement and are fully tested.

## Troubleshooting

### Orphaned Entries

If orphaned entries are found (non-zero values from `/admin/orphaned-entries`):

1. **Root Cause**: Likely caused by:
   - Direct SQL DELETE without CASCADE
   - Application-level deletion bypassing ORM
   - Historical bug before CASCADE was properly configured

2. **Resolution**:
   - Use `/admin/cleanup-orphaned` to remove orphans
   - Ensure all deletions go through SQLAlchemy ORM
   - Never use raw SQL DELETE on tables with foreign keys

### Failed Cascade

If CASCADE deletions fail:

1. Check that migrations are up to date: `alembic upgrade head`
2. Verify constraints exist in the actual database schema
3. Use `\d+ tablename` in psql to inspect foreign key constraints

### Duplicate Entry Violations

If unique constraint violations occur:

1. The application uses upsert logic for annotations (POST updates existing)
2. For other tables, check for race conditions in concurrent requests
3. Migration `d2e3f4g5h6i7` includes cleanup of historical duplicates
