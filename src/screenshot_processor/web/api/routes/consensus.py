from __future__ import annotations

import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from screenshot_processor.web.api.dependencies import CurrentAdmin, CurrentUser, DatabaseSession
from screenshot_processor.web.database import (
    ConsensusAnalysis,
    ConsensusSummaryResponse,
    DisagreementDetail,
    FieldDifference,
    GroupVerificationSummary,
    ResolveDisputeRequest,
    ResolveDisputeResponse,
    ScreenshotComparison,
    ScreenshotTierItem,
    VerifierAnnotation,
)
from screenshot_processor.web.database.models import Annotation, Screenshot
from screenshot_processor.web.repositories import ConsensusRepo, ScreenshotRepo
from screenshot_processor.web.services import ConsensusService

router = APIRouter(prefix="/consensus", tags=["Consensus"])


# =============================================================================
# Helper Functions
# =============================================================================


def _compare_annotations(annotations: list[Annotation]) -> tuple[bool, list[FieldDifference]]:
    """
    Compare annotations from multiple verifiers.
    Returns (has_agreement, differences).

    Strict comparison: ANY difference in hourly values, title, or total = disagreement.
    """
    if len(annotations) < 2:
        return True, []

    differences: list[FieldDifference] = []

    # Compare hourly values (hours 0-23)
    for hour in range(24):
        hour_key = str(hour)
        values: dict[str, int | float | None] = {}
        for ann in annotations:
            values[str(ann.user_id)] = ann.hourly_values.get(hour_key)

        # Check if all values are the same
        unique_values = {v for v in values.values() if v is not None}
        if len(unique_values) > 1:
            differences.append(FieldDifference(field=f"hourly_{hour}", values=values))

    # Compare extracted_title
    title_values: dict[str, str | None] = {}
    for ann in annotations:
        title_values[str(ann.user_id)] = ann.extracted_title
    unique_titles = {v for v in title_values.values() if v is not None}
    if len(unique_titles) > 1:
        differences.append(FieldDifference(field="title", values=title_values))

    # Compare extracted_total
    total_values: dict[str, str | None] = {}
    for ann in annotations:
        total_values[str(ann.user_id)] = ann.extracted_total
    unique_totals = {v for v in total_values.values() if v is not None}
    if len(unique_totals) > 1:
        differences.append(FieldDifference(field="total", values=total_values))

    has_agreement = len(differences) == 0
    return has_agreement, differences


def _get_verification_tier_with_diff(
    screenshot: Screenshot, annotations: list[Annotation]
) -> tuple[Literal["single_verified", "agreed", "disputed"], list[FieldDifference]]:
    """Determine the verification tier and differences for a screenshot."""
    verifier_ids = screenshot.verified_by_user_ids or []

    if len(verifier_ids) <= 1:
        return "single_verified", []

    # 2+ verifiers - check for agreement
    verified_annotations = [a for a in annotations if a.user_id in verifier_ids]
    has_agreement, differences = _compare_annotations(verified_annotations)
    tier = "agreed" if has_agreement else "disputed"
    return tier, differences


# =============================================================================
# Verification Tier Endpoints (MUST be before parameterized routes)
# =============================================================================


@router.get("/groups", response_model=list[GroupVerificationSummary])
async def get_groups_with_verification_tiers(
    repo: ConsensusRepo,
    current_user: CurrentUser,
):
    """
    Get all groups with verification tier breakdown.

    Returns groups with counts for:
    - single_verified: Verified by exactly 1 user
    - agreed: 2+ users verified, all values match exactly
    - disputed: 2+ users verified, any difference exists
    """

    # Get all groups with counts in a single query (eliminates N+1)
    groups_with_counts = await repo.get_all_groups_with_counts()

    summaries = []

    for row in groups_with_counts:
        group = row["group"]
        total_screenshots = row["total_screenshots"]

        # Get verified screenshots with eagerly loaded annotations for tier computation
        verified_screenshots = await repo.get_verified_screenshots_in_group(group.id)

        single_verified = 0
        agreed = 0
        disputed = 0

        for screenshot in verified_screenshots:
            tier, _ = _get_verification_tier_with_diff(screenshot, screenshot.annotations)
            if tier == "single_verified":
                single_verified += 1
            elif tier == "agreed":
                agreed += 1
            elif tier == "disputed":
                disputed += 1

        summaries.append(
            GroupVerificationSummary(
                id=group.id,
                name=group.name,
                image_type=group.image_type,
                single_verified=single_verified,
                agreed=agreed,
                disputed=disputed,
                total_verified=len(verified_screenshots),
                total_screenshots=total_screenshots,
            )
        )

    return summaries


@router.get("/groups/{group_id}/screenshots", response_model=list[ScreenshotTierItem])
async def get_screenshots_by_tier(
    group_id: str,
    repo: ConsensusRepo,
    current_user: CurrentUser,
    tier: Literal["single_verified", "agreed", "disputed"] = Query(..., description="Verification tier to filter by"),
):
    """
    Get screenshots in a specific verification tier for a group.
    """

    # Verify group exists
    group = await repo.get_group_by_id(group_id)

    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    # Get all verified screenshots in this group
    verified_screenshots = await repo.get_verified_screenshots_in_group(group_id)

    items = []
    for screenshot in verified_screenshots:
        verifier_ids = screenshot.verified_by_user_ids or []

        screenshot_tier, differences = _get_verification_tier_with_diff(screenshot, screenshot.annotations)

        if screenshot_tier == tier:
            items.append(
                ScreenshotTierItem(
                    id=screenshot.id,
                    file_path=screenshot.file_path,
                    participant_id=screenshot.participant_id,
                    screenshot_date=screenshot.screenshot_date,
                    verifier_count=len(verifier_ids),
                    has_differences=len(differences) > 0,
                    extracted_title=screenshot.extracted_title,
                )
            )

    return items


@router.get("/screenshots/{screenshot_id}/compare", response_model=ScreenshotComparison)
async def get_screenshot_comparison(
    screenshot_id: int,
    repo: ConsensusRepo,
    current_user: CurrentUser,
):
    """
    Get comparison data for a screenshot with multiple verifiers.
    Shows each verifier's annotation and highlights differences.
    """

    # Get screenshot with annotations and resolved_by user
    screenshot = await repo.get_screenshot_with_annotations(screenshot_id)

    if not screenshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")

    verifier_ids = screenshot.verified_by_user_ids or []
    if len(verifier_ids) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Screenshot has no verified annotations")

    # Get annotations from verified users
    verified_annotations = [a for a in screenshot.annotations if a.user_id in verifier_ids]
    annotation_user_ids = {a.user_id for a in verified_annotations}

    # Build verifier annotation list
    verifier_annotations = []
    for ann in verified_annotations:
        verifier_annotations.append(
            VerifierAnnotation(
                user_id=ann.user_id,
                username=ann.user.username if ann.user else f"User {ann.user_id}",
                hourly_values=ann.hourly_values,
                extracted_title=ann.extracted_title,
                extracted_total=ann.extracted_total,
                verified_at=ann.updated_at,
            )
        )

    # Handle verifiers who don't have explicit annotation records
    # They verified using the screenshot's extracted data
    missing_verifier_ids = [vid for vid in verifier_ids if vid not in annotation_user_ids]
    if missing_verifier_ids:
        # Look up usernames for verifiers without annotations
        users = await repo.get_users_by_ids(missing_verifier_ids)
        users_by_id = {u.id: u for u in users}

        for vid in missing_verifier_ids:
            user = users_by_id.get(vid)
            verifier_annotations.append(
                VerifierAnnotation(
                    user_id=vid,
                    username=user.username if user else f"User {vid}",
                    hourly_values=screenshot.extracted_hourly_data or {},
                    extracted_title=screenshot.extracted_title,
                    extracted_total=screenshot.extracted_total,
                    verified_at=screenshot.uploaded_at,  # Use screenshot upload time as proxy
                )
            )

    # Compare annotations
    has_agreement, differences = _compare_annotations(verified_annotations)
    tier, _ = _get_verification_tier_with_diff(screenshot, screenshot.annotations)

    # Determine resolution status
    is_resolved = screenshot.resolved_at is not None

    return ScreenshotComparison(
        screenshot_id=screenshot.id,
        file_path=screenshot.file_path,
        group_id=screenshot.group_id,
        participant_id=screenshot.participant_id,
        screenshot_date=screenshot.screenshot_date,
        tier=tier,
        verifier_annotations=verifier_annotations,
        differences=differences,
        is_resolved=is_resolved,
        resolved_at=screenshot.resolved_at,
        resolved_by_user_id=screenshot.resolved_by_user_id,
        resolved_by_username=screenshot.resolved_by.username if screenshot.resolved_by else None,
        resolved_hourly_data=screenshot.resolved_hourly_data,
        resolved_title=screenshot.resolved_title,
        resolved_total=screenshot.resolved_total,
    )


@router.post("/screenshots/{screenshot_id}/resolve", response_model=ResolveDisputeResponse)
async def resolve_dispute(
    screenshot_id: int,
    request: ResolveDisputeRequest,
    screenshot_repo: ScreenshotRepo,
    admin: CurrentAdmin,
):
    """
    Resolve a dispute by setting the final agreed-upon values.

    Requires admin role. Updates the screenshot's extracted_* fields directly
    (like a normal GUI edit), so changes are immediately visible everywhere.
    Original OCR values are preserved in resolved_* fields for audit/rollback.
    """
    # Get screenshot with row lock
    screenshot = await screenshot_repo.get_by_id_for_update(screenshot_id)

    if not screenshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")

    verifier_ids = screenshot.verified_by_user_ids or []
    if len(verifier_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Screenshot does not have multiple verifiers to resolve"
        )

    # Store ORIGINAL values in resolved_* fields for audit/rollback
    screenshot.resolved_hourly_data = screenshot.extracted_hourly_data
    screenshot.resolved_title = screenshot.extracted_title
    screenshot.resolved_total = screenshot.extracted_total

    # Update extracted_* fields directly (like a GUI edit) - visible everywhere immediately
    screenshot.extracted_hourly_data = request.hourly_values
    if request.extracted_title is not None:
        screenshot.extracted_title = request.extracted_title
    if request.extracted_total is not None:
        screenshot.extracted_total = request.extracted_total

    # Track who resolved and when
    screenshot.resolved_at = datetime.datetime.now(datetime.timezone.utc)
    screenshot.resolved_by_user_id = admin.id

    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(screenshot, "extracted_hourly_data")
    flag_modified(screenshot, "resolved_hourly_data")

    try:
        await screenshot_repo.db.commit()
    except Exception as e:
        await screenshot_repo.db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve dispute",
        ) from e

    return ResolveDisputeResponse(
        success=True,
        screenshot_id=screenshot_id,
        message="Dispute resolved. Values updated and visible in queue. Original OCR values preserved for rollback.",
        resolved_at=screenshot.resolved_at,
        resolved_by_user_id=admin.id,
        resolved_by_username=admin.username,
    )


# =============================================================================
# Summary Stats Endpoint
# =============================================================================


@router.get("/summary/stats", response_model=ConsensusSummaryResponse)
async def get_consensus_summary(db: DatabaseSession, current_user: CurrentUser):
    """Get summary statistics for consensus analysis."""
    summary = await ConsensusService.get_consensus_summary(db)

    return ConsensusSummaryResponse(
        total_screenshots=summary.get("total_completed_screenshots", 0),
        screenshots_with_consensus=summary.get("screenshots_with_consensus", 0),
        screenshots_with_disagreements=summary.get("screenshots_with_disagreements", 0),
        total_disagreements=0,
        avg_disagreements_per_screenshot=0.0,
    )


# =============================================================================
# Parameterized Endpoints (MUST be after static routes to avoid path conflicts)
# =============================================================================


@router.get("/{screenshot_id}", response_model=ConsensusAnalysis)
async def get_consensus_analysis(screenshot_id: int, db: DatabaseSession, current_user: CurrentUser):
    """Get consensus analysis for a specific screenshot."""
    analysis = await ConsensusService.analyze_consensus(db, screenshot_id)

    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")

    return _build_consensus_analysis(analysis)


def _build_consensus_analysis(analysis: dict) -> ConsensusAnalysis:
    """Build ConsensusAnalysis response from service analysis dict."""
    disagreements = [
        DisagreementDetail(
            hour=d["hour"],
            values=d["values"],
            median=d["median"],
            has_disagreement=d["has_disagreement"],
            max_difference=d["max_difference"],
        )
        for d in analysis["disagreements"]
    ]

    return ConsensusAnalysis(
        screenshot_id=analysis["screenshot_id"],
        has_consensus=analysis["has_consensus"],
        total_annotations=analysis["total_annotations"],
        disagreements=disagreements,
        consensus_hourly_values=analysis["consensus_hourly_values"],
        calculated_at=datetime.datetime.now(datetime.timezone.utc),
    )


@router.post("/{screenshot_id}/recalculate", response_model=ConsensusAnalysis)
async def recalculate_consensus(screenshot_id: int, db: DatabaseSession, current_user: CurrentUser):
    """Recalculate consensus for a specific screenshot."""
    analysis = await ConsensusService.analyze_consensus(db, screenshot_id)

    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")

    return _build_consensus_analysis(analysis)
