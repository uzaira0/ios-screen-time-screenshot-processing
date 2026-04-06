# Workflow Engine Design — Screenshot Preprocessing

## Context

The preprocessing pipeline (device_detection → cropping → phi_detection → phi_redaction → ocr) currently uses Celery for task dispatch and a JSON blob (`Screenshot.processing_metadata`) for state tracking. This causes: flat retry delays, no within-task progress, unbounded JSON event logs, no queryable execution history, stuck-state issues on worker crash, and duplicated ordering logic across tasks/API/frontend.

This design replaces both Celery and the JSON blob with a Temporal-compatible workflow engine backed by PostgreSQL tables. The engine is a copy of the pattern from `/home/opt/sleep-scoring-web/workflows/engine/`, adapted for this project's preprocessing pipeline.

## Architecture

### Two Workflows, Five Activities

The pipeline splits at the human-in-the-loop boundary:

| Workflow | Stages | Trigger | Lifecycle |
|----------|--------|---------|-----------|
| `PreprocessingWorkflow` | device_detection → cropping → phi_detection | User clicks "Run preprocessing" or upload completes | Automated, seconds to minutes |
| `RedactionWorkflow` | phi_redaction → ocr | User clicks "Apply redaction" after reviewing PHI regions | User-triggered, seconds |

Each stage is a registered `@activity.defn` function. One workflow instance per screenshot.

### Engine Components

Ported from sleep-scoring-web with minimal adaptation:

```
src/screenshot_processor/workflows/engine/
├── __init__.py          # Public API re-export
├── types.py             # RetryPolicy, ActivityInfo, NonRetryableError, status enums
├── registry.py          # Workflow/activity registration via decorators
├── workflow.py          # @workflow.defn, @workflow.run, @workflow.signal, @workflow.query, execute_activity()
├── activity.py          # @activity.defn, heartbeat(), info() via contextvars
├── models.py            # WorkflowExecution, ActivityExecution, WorkflowSignal (SQLAlchemy)
└── worker.py            # Error classification, retry backoff, execute_activity_with_persistence()
```

### Database Tables (replace JSON blob)

**`workflow_execution`**

| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| screenshot_id | int FK → screenshots.id | Indexed |
| workflow_type | str(64) | "preprocessing" or "redaction" |
| status | str(20) | pending, running, completed, failed, cancelled |
| current_activity | str(64) NULL | Name of activity currently executing |
| created_at | datetime(tz) | Auto-set |
| updated_at | datetime(tz) | Auto-updated |

Constraint: unique partial index on `(screenshot_id, workflow_type) WHERE status IN ('pending', 'running')` — one *active* workflow per type per screenshot. Completed/failed workflows are kept for audit history.

**`activity_execution`**

| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| workflow_id | int FK → workflow_execution.id | Cascade delete, indexed |
| activity_name | str(64) | "device_detection", "cropping", etc. |
| status | str(20) | pending, running, completed, failed, skipped |
| attempt | int | 1-based retry count |
| progress_pct | float | 0.0–100.0, updated via heartbeat |
| error_message | text NULL | Full traceback on failure |
| error_class | str(20) NULL | "transient" or "permanent" |
| started_at | datetime(tz) NULL | |
| completed_at | datetime(tz) NULL | |
| result_json | jsonb NULL | Activity output (device info, crop dimensions, PHI regions, etc.) |

**`workflow_signal`**

| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| workflow_id | int FK → workflow_execution.id | Cascade delete |
| signal_name | str(64) | |
| payload_json | jsonb NULL | |
| consumed | bool | Default false |
| created_at | datetime(tz) | |

Index on `(workflow_id, consumed)`.

### Workflow Definitions

```python
@workflow.defn
class PreprocessingWorkflow:
    @workflow.run
    async def run(self, screenshot_id: int) -> None:
        await workflow.execute_activity(
            device_detection,
            args=[screenshot_id],
            retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5)),
        )
        await workflow.execute_activity(
            cropping,
            args=[screenshot_id],
            retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5)),
        )
        await workflow.execute_activity(
            phi_detection,
            args=[screenshot_id],
            retry_policy=RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=30)),
            heartbeat_timeout=timedelta(seconds=120),
        )

@workflow.defn
class RedactionWorkflow:
    @workflow.run
    async def run(self, screenshot_id: int) -> None:
        await workflow.execute_activity(
            phi_redaction,
            args=[screenshot_id],
            retry_policy=RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=10)),
        )
        await workflow.execute_activity(
            ocr_extraction,
            args=[screenshot_id],
            retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=10)),
        )
```

### Activity Definitions

Each activity is a standalone function with `@activity.defn`. Activities read/write files on disk and update Screenshot fields. They report progress via `activity.heartbeat()`.

```python
@activity.defn
async def device_detection(screenshot_id: int) -> dict:
    activity.heartbeat(0)
    # Load image, detect device, return result dict
    activity.heartbeat(100)
    return {"device_category": "iphone", "confidence": 0.98, ...}

@activity.defn
async def phi_detection(screenshot_id: int) -> dict:
    activity.heartbeat(0)
    # Run OCR + NER + regex, report incremental progress
    activity.heartbeat(30)  # OCR done
    activity.heartbeat(60)  # NER done
    activity.heartbeat(90)  # Regex done
    activity.heartbeat(100)
    return {"phi_detected": True, "regions_count": 3, "regions": [...]}
```

Activity results are stored in `activity_execution.result_json`. No more appending to a JSON blob on the Screenshot model.

### Worker

A DB-polling async worker replaces Celery:

```python
class WorkflowWorker:
    def __init__(self, db_session_factory, concurrency=4):
        ...

    async def run(self):
        """Poll loop: find pending activities, execute with retry."""
        while True:
            activities = await self.poll_pending(limit=self.concurrency)
            if activities:
                await asyncio.gather(*[
                    self.execute_one(act) for act in activities
                ])
            else:
                await asyncio.sleep(1)
```

- Polls `activity_execution` for `status='pending'` rows
- Executes via `execute_activity_with_persistence()` (handles retries, error classification, heartbeat)
- Configurable concurrency (default 4, matching current Celery worker count)
- On startup: resets any `status='running'` activities to `'pending'` (crash recovery — replaces the band-aid reconciliation code)

### Worker Deployment

The worker runs as a standalone process, replacing the Celery worker + Redis:

```bash
# Current (remove)
celery -A screenshot_processor.web.celery_app worker --concurrency=8

# New
python -m screenshot_processor.workflows.worker --concurrency=4
```

Or embedded in the FastAPI process as a background task for simpler deployment:

```python
@app.on_event("startup")
async def start_worker():
    worker = WorkflowWorker(async_session_maker, concurrency=4)
    asyncio.create_task(worker.run())
```

### API Changes

Existing API routes (`/preprocess-stage/{stage}`, `/preprocess-batch`) change from dispatching Celery tasks to creating workflow/activity rows:

```python
# Before (Celery)
task = device_detection_task.apply_async(args=[screenshot_id])
return {"task_ids": [task.id]}

# After (Workflow engine)
wf = WorkflowExecution(screenshot_id=id, workflow_type="preprocessing", status="pending")
db.add(wf)
# Activities created by worker when workflow starts
return {"workflow_id": wf.id}
```

Progress queries change from parsing JSON to simple SQL:

```python
# Before
pp = screenshot.processing_metadata.get("preprocessing", {})
status = pp.get("stage_status", {}).get("device_detection", "pending")

# After
activity = await db.execute(
    select(ActivityExecution)
    .join(WorkflowExecution)
    .where(WorkflowExecution.screenshot_id == id)
    .where(ActivityExecution.activity_name == "device_detection")
)
status = activity.scalar_one_or_none()?.status
```

### Migration from JSON Blob

1. New tables created via Alembic migration
2. Existing `processing_metadata` JSON data migrated to `workflow_execution` + `activity_execution` rows (one-time script)
3. `processing_metadata` column kept but deprecated — no new writes
4. Frontend switches from reading JSON to querying new API endpoints backed by the tables
5. After validation, `processing_metadata` column dropped in a follow-up migration

### What Gets Removed

| Component | Replacement |
|-----------|-------------|
| `celery_app.py` | Deleted |
| `tasks.py` (Celery tasks) | `@activity.defn` functions |
| Redis dependency | Removed from docker-compose |
| `processing_metadata` JSON blob | `workflow_execution` + `activity_execution` tables |
| Stuck-state reconciliation (durability hardening) | Worker startup reset (built into engine) |
| `STAGE_ORDER` list in pipeline.py | Workflow `@workflow.run` method defines order |
| Manual event log management | `activity_execution` rows with `result_json` |

### What Stays

- The actual processing logic (device detection, cropping, PHI detection, etc.) — just wrapped in `@activity.defn`
- The WASM-mode preprocessing service (client-side, unaffected)
- The frontend preprocessing UI (reads from new API endpoints instead of JSON)
- PostgreSQL as the database
- Docker-based deployment

## Retry Policies

| Activity | max_attempts | initial_interval | backoff | non_retryable |
|----------|-------------|-------------------|---------|---------------|
| device_detection | 3 | 5s | 2.0x | ValueError, FileNotFoundError |
| cropping | 3 | 5s | 2.0x | ValueError, FileNotFoundError |
| phi_detection | 2 | 30s | 2.0x | ValueError, FileNotFoundError |
| phi_redaction | 2 | 10s | 2.0x | ValueError, FileNotFoundError |
| ocr_extraction | 3 | 10s | 2.0x | ValueError, FileNotFoundError |

## Verification Plan

1. **Unit tests**: Registry, decorators, error classification, retry computation (port from sleep-scoring-web)
2. **Integration tests**: `execute_activity_with_persistence()` with real DB — activity succeeds, fails transiently (retries), fails permanently (no retry)
3. **Workflow tests**: Create `PreprocessingWorkflow`, run worker, verify all 3 activities execute in order and results stored in DB
4. **Migration test**: Run migration script on existing data, verify `activity_execution` rows match prior `processing_metadata` events
5. **API test**: Hit `/preprocess-stage/device_detection`, verify workflow created and activity completes
6. **E2E test**: Upload screenshot → preprocessing workflow runs → review PHI → trigger redaction workflow → OCR completes → verify all `activity_execution` rows
