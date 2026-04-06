"""WorkflowWorker — DB-polling async worker that executes workflow activities.

Replaces Celery workers. Polls workflow_execution/activity_execution tables
for pending work and executes activities with retry logic.

Usage:
    python -m screenshot_processor.workflows.worker_main [--concurrency=4] [--poll-interval=1.0]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys

from datetime import UTC, datetime

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("screenshot_processor.workflows.worker")


def _get_sync_session_factory() -> sessionmaker:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://screenshot:screenshot@localhost:5433/screenshot_annotations",
    )
    SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class WorkflowWorker:
    """Polls DB for pending workflows and executes their activities sequentially."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        concurrency: int = 4,
        poll_interval: float = 1.0,
    ):
        self.session_factory = session_factory
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self._shutdown = False
        self._semaphore = asyncio.Semaphore(concurrency)

    async def startup(self) -> None:
        """Crash recovery: reset any activities stuck in 'running' from a previous crash."""
        from screenshot_processor.workflows.engine.models import ActivityExecution, WorkflowExecution
        from screenshot_processor.workflows.engine.types import ActivityStatus, WorkflowStatus

        db = self.session_factory()
        try:
            # Reset stuck activities
            stuck_activities = (
                db.query(ActivityExecution)
                .filter(ActivityExecution.status == ActivityStatus.RUNNING)
                .all()
            )
            for act in stuck_activities:
                act.status = ActivityStatus.PENDING
                act.started_at = None

            # Reset stuck workflows
            stuck_workflows = (
                db.query(WorkflowExecution)
                .filter(WorkflowExecution.status == WorkflowStatus.RUNNING)
                .all()
            )
            for wf in stuck_workflows:
                wf.status = WorkflowStatus.PENDING

            if stuck_activities or stuck_workflows:
                db.commit()
                logger.info(
                    "Crash recovery: reset %d stuck activities, %d stuck workflows",
                    len(stuck_activities), len(stuck_workflows),
                )
        finally:
            db.close()

    async def run(self) -> None:
        """Main poll loop."""
        await self.startup()
        logger.info("Worker started (concurrency=%d, poll_interval=%.1fs)", self.concurrency, self.poll_interval)

        while not self._shutdown:
            try:
                workflows = self._poll_pending_workflows()
                if workflows:
                    tasks = []
                    for wf_id in workflows:
                        tasks.append(self._process_workflow(wf_id))
                    await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    await asyncio.sleep(self.poll_interval)
            except Exception:
                logger.exception("Worker loop error")
                await asyncio.sleep(self.poll_interval)

    def _poll_pending_workflows(self) -> list[int]:
        """Find pending workflows ready for execution."""
        from screenshot_processor.workflows.engine.models import WorkflowExecution
        from screenshot_processor.workflows.engine.types import WorkflowStatus

        db = self.session_factory()
        try:
            results = (
                db.query(WorkflowExecution.id)
                .filter(WorkflowExecution.status.in_([WorkflowStatus.PENDING, WorkflowStatus.RUNNING]))
                .order_by(WorkflowExecution.created_at)
                .limit(self.concurrency)
                .all()
            )
            return [r[0] for r in results]
        finally:
            db.close()

    async def _process_workflow(self, workflow_id: int) -> None:
        """Process a single workflow: execute its next pending activity."""
        async with self._semaphore:
            await asyncio.get_event_loop().run_in_executor(
                None, self._process_workflow_sync, workflow_id
            )

    def _process_workflow_sync(self, workflow_id: int) -> None:
        """Synchronous workflow processing (runs in thread pool)."""
        from screenshot_processor.workflows.engine.models import ActivityExecution, WorkflowExecution
        from screenshot_processor.workflows.engine.types import ActivityStatus, WorkflowStatus
        from screenshot_processor.workflows.engine.worker import (
            classify_error,
            compute_retry_delay,
            execute_activity_with_persistence,
            should_retry,
        )
        from screenshot_processor.workflows.engine.types import RetryPolicy

        db = self.session_factory()
        try:
            wf = db.query(WorkflowExecution).filter(WorkflowExecution.id == workflow_id).first()
            if not wf:
                return

            # Mark workflow as running
            if wf.status == WorkflowStatus.PENDING:
                wf.status = WorkflowStatus.RUNNING
                db.commit()

            # Find next pending activity
            next_act = (
                db.query(ActivityExecution)
                .filter(
                    ActivityExecution.workflow_id == workflow_id,
                    ActivityExecution.status == ActivityStatus.PENDING,
                )
                .order_by(ActivityExecution.id)
                .first()
            )

            if not next_act:
                # All activities done — check if any failed
                failed = (
                    db.query(ActivityExecution)
                    .filter(
                        ActivityExecution.workflow_id == workflow_id,
                        ActivityExecution.status == ActivityStatus.FAILED,
                    )
                    .count()
                )
                wf.status = WorkflowStatus.FAILED if failed else WorkflowStatus.COMPLETED
                wf.current_activity = None
                db.commit()
                logger.info("Workflow %d %s", workflow_id, wf.status)
                return

            # Execute the activity
            wf.current_activity = next_act.activity_name
            db.commit()

            # Default retry policy if none specified
            policy = RetryPolicy(maximum_attempts=3)

            try:
                # Run synchronously — execute_activity_with_persistence is async
                # but uses sync DB session, so we run it in an event loop
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        execute_activity_with_persistence(
                            db, next_act, args=self._get_activity_args(wf, next_act), retry_policy=policy,
                        )
                    )
                finally:
                    loop.close()

            except Exception as exc:
                error_class = classify_error(exc, policy=policy)
                if should_retry(policy, attempt=next_act.attempt, error_class=error_class):
                    # Reset for retry
                    delay = compute_retry_delay(policy, attempt=next_act.attempt)
                    next_act.status = ActivityStatus.PENDING
                    next_act.attempt += 1
                    next_act.error_message = None
                    next_act.error_class = None
                    next_act.completed_at = None
                    db.commit()
                    logger.info(
                        "Activity %s attempt %d failed (%s), retrying in %s",
                        next_act.activity_name, next_act.attempt - 1, error_class, delay,
                    )
                    import time
                    time.sleep(delay.total_seconds())
                else:
                    # Permanent failure — mark workflow as failed
                    wf.status = WorkflowStatus.FAILED
                    db.commit()
                    logger.error(
                        "Activity %s failed permanently: %s",
                        next_act.activity_name, exc,
                    )
        except Exception:
            logger.exception("Error processing workflow %d", workflow_id)
        finally:
            db.close()

    def _get_activity_args(self, wf, act) -> list:
        """Build args list for an activity based on workflow context."""
        # All activities take screenshot_id as first arg
        return [wf.screenshot_id]

    def shutdown(self) -> None:
        """Signal the worker to stop after current work completes."""
        logger.info("Shutdown requested")
        self._shutdown = True


async def main(concurrency: int = 4, poll_interval: float = 1.0) -> None:
    """Entry point for the workflow worker."""
    # Import workflow definitions to register them
    import screenshot_processor.workflows.definitions  # noqa: F401

    session_factory = _get_sync_session_factory()
    worker = WorkflowWorker(session_factory, concurrency=concurrency, poll_interval=poll_interval)

    # Handle signals for graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.shutdown)

    await worker.run()


def cli() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Screenshot preprocessing workflow worker")
    parser.add_argument("--concurrency", type=int, default=4, help="Max concurrent workflows (default: 4)")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main(concurrency=args.concurrency, poll_interval=args.poll_interval))


if __name__ == "__main__":
    cli()
