"""
Celery application for background task processing.

This module configures Celery with Redis as the message broker and result backend.
Tasks are defined for screenshot processing (OCR, grid detection, etc.)
"""

import logging
import os

from celery import Celery

logger = logging.getLogger(__name__)

# Get Redis URL from environment
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "screenshot_processor",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["screenshot_processor.web.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,  # Acknowledge task after completion (reliability)
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    # Result expiration (1 hour)
    result_expires=3600,
    # Worker settings
    worker_prefetch_multiplier=2,  # Prefetch 2 tasks per worker for better throughput
    worker_concurrency=8,  # Number of concurrent workers (overridden by --concurrency CLI flag)
    # Route fast tasks (redaction, OCR, device detection) to a separate queue so
    # they are never blocked behind slow PHI detection tasks.
    task_routes={
        "screenshot_processor.web.tasks.phi_redaction_task": {"queue": "fast"},
        "screenshot_processor.web.tasks.ocr_stage_task": {"queue": "fast"},
        "screenshot_processor.web.tasks.device_detection_task": {"queue": "fast"},
        "screenshot_processor.web.tasks.cropping_task": {"queue": "fast"},
    },
    task_default_queue="default",
)


from celery.signals import worker_ready


@worker_ready.connect
def _reset_stuck_running_stages(sender, **kwargs):
    """Reset any preprocessing stages stuck in 'running' from a previous worker crash.

    When a worker is killed mid-task (restart, OOM, timeout), the stage status
    stays as 'running' forever. This runs once on worker startup to clean them up.
    """

    def _cleanup():
        try:
            from sqlalchemy import create_engine, text

            from screenshot_processor.web.config import get_settings

            settings = get_settings()
            sync_url = str(settings.DATABASE_URL).replace("+asyncpg", "")
            engine = create_engine(sync_url)
            with engine.begin() as conn:
                # Find all screenshots with any stage in 'running'
                rows = conn.execute(text(
                    "SELECT id, processing_metadata FROM screenshots "
                    "WHERE processing_metadata::text LIKE '%\"running\"%'"
                )).fetchall()

                if not rows:
                    return

                for row in rows:
                    sid = row[0]
                    meta = row[1]
                    pp = (meta or {}).get("preprocessing", {})
                    stage_status = pp.get("stage_status", {})
                    changed = False
                    for stage, status in stage_status.items():
                        if status == "running":
                            stage_status[stage] = "pending"
                            changed = True
                    if changed:
                        import json
                        conn.execute(
                            text("UPDATE screenshots SET processing_metadata = :meta WHERE id = :id"),
                            {"meta": json.dumps(meta), "id": sid},
                        )

                logger.info("Startup cleanup: reset %d stuck 'running' stages to 'pending'", len(rows))
            engine.dispose()
        except Exception as e:
            logger.warning("Startup cleanup failed (non-fatal): %s", e)

    # Run synchronously so cleanup completes before tasks start
    _cleanup()
