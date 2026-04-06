"""Workflow definitions for the preprocessing pipeline.

Two workflows, split at the human-in-the-loop boundary:
- PreprocessingWorkflow: stages 1-3 (automated)
- RedactionWorkflow: stages 4-5 (user-triggered after PHI review)

When migrating to Temporal, change the import to:
    from temporalio import workflow
"""

from __future__ import annotations

from datetime import timedelta

from screenshot_processor.workflows.activities import (
    cropping,
    device_detection,
    ocr_extraction,
    phi_detection,
    phi_redaction,
)
from screenshot_processor.workflows.engine import workflow
from screenshot_processor.workflows.engine.types import RetryPolicy


@workflow.defn
class PreprocessingWorkflow:
    """Automated preprocessing: device detection → cropping → PHI detection.

    Created when user clicks "Run preprocessing" or on upload.
    Runs to completion in seconds to minutes. After completion,
    user reviews PHI regions before triggering RedactionWorkflow.
    """

    @workflow.run
    async def run(self, screenshot_id: int) -> None:
        await workflow.execute_activity(
            device_detection,
            args=[screenshot_id],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                non_retryable_error_types=["ValueError", "FileNotFoundError"],
            ),
        )
        await workflow.execute_activity(
            cropping,
            args=[screenshot_id],
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                non_retryable_error_types=["ValueError", "FileNotFoundError"],
            ),
        )
        await workflow.execute_activity(
            phi_detection,
            args=[screenshot_id],
            start_to_close_timeout=timedelta(seconds=300),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
                initial_interval=timedelta(seconds=30),
                non_retryable_error_types=["ValueError", "FileNotFoundError"],
            ),
        )

    @workflow.signal
    async def cancel(self) -> None:
        """Cancel the workflow. Worker checks for this signal between activities."""


@workflow.defn
class RedactionWorkflow:
    """User-triggered: PHI redaction → OCR extraction.

    Created when user clicks "Apply redaction" after reviewing PHI regions.
    """

    @workflow.run
    async def run(self, screenshot_id: int) -> None:
        await workflow.execute_activity(
            phi_redaction,
            args=[screenshot_id],
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
                initial_interval=timedelta(seconds=10),
                non_retryable_error_types=["ValueError", "FileNotFoundError"],
            ),
        )
        await workflow.execute_activity(
            ocr_extraction,
            args=[screenshot_id],
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=10),
                non_retryable_error_types=["ValueError", "FileNotFoundError"],
            ),
        )
