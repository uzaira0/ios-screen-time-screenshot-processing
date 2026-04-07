from __future__ import annotations

import os
import statistics
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.consensus_repository import ConsensusRepository


class ConsensusStrategy(str, Enum):
    MEDIAN = "median"
    MODE = "mode"
    MEAN = "mean"


class DisagreementSeverity(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"


class ConsensusService:
    # Thresholds configurable via environment variables
    # Default: any difference flags for review (threshold=0)
    DISAGREEMENT_THRESHOLD_MINUTES = int(os.getenv("CONSENSUS_DISAGREEMENT_THRESHOLD_MINUTES", "0"))
    MINOR_THRESHOLD = int(os.getenv("CONSENSUS_MINOR_THRESHOLD", "2"))
    MODERATE_THRESHOLD = int(os.getenv("CONSENSUS_MODERATE_THRESHOLD", "5"))

    @staticmethod
    def classify_disagreement_severity(max_diff: float) -> DisagreementSeverity:
        if max_diff == 0:
            return DisagreementSeverity.NONE
        elif max_diff <= ConsensusService.MINOR_THRESHOLD:
            return DisagreementSeverity.MINOR
        elif max_diff <= ConsensusService.MODERATE_THRESHOLD:
            return DisagreementSeverity.MODERATE
        else:
            return DisagreementSeverity.MAJOR

    @staticmethod
    def calculate_consensus_value(values: list[float], strategy: ConsensusStrategy = ConsensusStrategy.MEDIAN) -> float:
        if not values:
            return 0.0

        if strategy == ConsensusStrategy.MEDIAN:
            return statistics.median(values)
        elif strategy == ConsensusStrategy.MEAN:
            return statistics.mean(values)
        elif strategy == ConsensusStrategy.MODE:
            try:
                return statistics.mode(values)
            except statistics.StatisticsError:
                return statistics.median(values)
        else:
            return statistics.median(values)

    @staticmethod
    async def analyze_consensus(
        db: AsyncSession,
        screenshot_id: int,
        strategy: ConsensusStrategy = ConsensusStrategy.MEDIAN,
    ) -> dict | None:
        repo = ConsensusRepository(db)

        # Use SELECT FOR UPDATE to lock the screenshot row and prevent race conditions
        # when multiple annotations are submitted concurrently
        screenshot = await repo.get_screenshot_with_annotations_for_update(screenshot_id)

        if not screenshot:
            return None

        annotations = screenshot.annotations
        if len(annotations) < 2:
            return {
                "screenshot_id": screenshot_id,
                "has_consensus": True,
                "total_annotations": len(annotations),
                "disagreements": [],
                "consensus_hourly_values": None,
            }

        all_hours = set()
        for annotation in annotations:
            all_hours.update(annotation.hourly_values.keys())

        disagreements = []
        consensus_values = {}

        for hour in sorted(all_hours):
            values = []
            for annotation in annotations:
                if hour in annotation.hourly_values:
                    value = float(annotation.hourly_values[hour])
                    values.append(value)

            if not values:
                continue

            consensus_value = ConsensusService.calculate_consensus_value(values, strategy)
            max_diff = max(abs(v - consensus_value) for v in values)
            severity = ConsensusService.classify_disagreement_severity(max_diff)
            has_disagreement = max_diff > ConsensusService.DISAGREEMENT_THRESHOLD_MINUTES

            if has_disagreement:
                disagreements.append(
                    {
                        "hour": hour,
                        "values": values,
                        "consensus_value": consensus_value,
                        "median": consensus_value,  # Alias for backward compatibility
                        "has_disagreement": True,
                        "max_difference": max_diff,
                        "severity": severity.value,
                        "strategy_used": strategy.value,
                    }
                )

            consensus_values[hour] = consensus_value

        has_consensus = len(disagreements) == 0

        existing_consensus = await repo.get_consensus_result(screenshot_id)

        disagreement_details = {
            "total_disagreements": len(disagreements),
            "disagreement_hours": [d["hour"] for d in disagreements],
            "details": disagreements,
        }

        if existing_consensus:
            existing_consensus.has_consensus = has_consensus
            existing_consensus.disagreement_details = disagreement_details
            existing_consensus.consensus_values = consensus_values if has_consensus else None
        else:
            from ..database.models import ConsensusResult as ConsensusResultModel

            new_consensus = ConsensusResultModel(
                screenshot_id=screenshot_id,
                has_consensus=has_consensus,
                disagreement_details=disagreement_details,
                consensus_values=consensus_values if has_consensus else None,
            )
            db.add(new_consensus)

        screenshot.has_consensus = has_consensus

        await db.commit()

        return {
            "screenshot_id": screenshot_id,
            "has_consensus": has_consensus,
            "has_disagreements": len(disagreements) > 0,
            "total_annotations": len(annotations),
            "disagreements": disagreements,
            "consensus_hourly_values": consensus_values if has_consensus else None,
            "strategy_used": strategy.value,
        }

    @staticmethod
    async def get_consensus_summary(db: AsyncSession) -> dict:
        repo = ConsensusRepository(db)
        counts = await repo.get_consensus_counts()

        total_with_consensus = counts["total_with_consensus"]
        total_with_disagreements = counts["total_with_disagreements"]
        total_completed = counts["total_completed"]

        return {
            "total_completed_screenshots": total_completed,
            "screenshots_with_consensus": total_with_consensus,
            "screenshots_with_disagreements": total_with_disagreements,
            "consensus_rate": ((total_with_consensus / total_completed * 100) if total_completed > 0 else 0.0),
        }
