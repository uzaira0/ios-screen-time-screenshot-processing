from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from screenshot_processor.web.api.dependencies import CurrentUser, DatabaseSession, get_screenshot_for_update
from screenshot_processor.web.cache import invalidate_stats_and_groups
from screenshot_processor.web.database import (
    Annotation,
    AnnotationCreate,
    AnnotationRead,
    AnnotationStatus,
    AnnotationUpdate,
    AnnotationWithIssues,
    ProcessingIssueRead,
)
from screenshot_processor.web.database.models import AnnotationAuditLog, SubmissionStatus, UserRole
from screenshot_processor.web.repositories import AnnotationRepo, ScreenshotRepo
from screenshot_processor.web.services import ConsensusService


def annotation_to_dict(annotation: Annotation) -> dict:
    """Convert annotation to dict for audit logging."""
    return {
        "hourly_values": annotation.hourly_values,
        "extracted_title": annotation.extracted_title,
        "extracted_total": annotation.extracted_total,
        "grid_upper_left": annotation.grid_upper_left,
        "grid_lower_right": annotation.grid_lower_right,
        "time_spent_seconds": annotation.time_spent_seconds,
        "notes": annotation.notes,
        "status": annotation.status,
    }


def summarize_changes(old_values: dict, new_values: dict) -> str:
    """Generate human-readable summary of changes."""
    changes = []
    for key in set(list(old_values.keys()) + list(new_values.keys())):
        old_val = old_values.get(key)
        new_val = new_values.get(key)
        if old_val != new_val:
            if key == "hourly_values":
                # Count how many hourly values changed
                old_hours = old_val or {}
                new_hours = new_val or {}
                if old_hours and new_hours:
                    diff_count = sum(1 for h in range(24) if old_hours.get(str(h)) != new_hours.get(str(h)))
                    changes.append(f"hourly_values: {diff_count} hours changed")
                else:
                    changes.append(f"hourly_values: set to {len(new_hours)} values")
            else:
                changes.append(f"{key}: {old_val!r} → {new_val!r}")
    return "; ".join(changes) if changes else "No changes"


async def create_audit_log(
    db,
    annotation_id: int,
    screenshot_id: int,
    user_id: int,
    action: str,
    previous_values: dict | None = None,
    new_values: dict | None = None,
) -> None:
    """Create an audit log entry for an annotation change."""
    summary = None
    if previous_values and new_values:
        summary = summarize_changes(previous_values, new_values)
    elif action == "created" and new_values:
        summary = f"Created with {len(new_values.get('hourly_values', {}))} hourly values"
    elif action == "deleted":
        summary = "Annotation deleted"

    audit_log = AnnotationAuditLog(
        annotation_id=annotation_id,
        screenshot_id=screenshot_id,
        user_id=user_id,
        action=action,
        previous_values=previous_values,
        new_values=new_values,
        changes_summary=summary,
    )
    db.add(audit_log)


def convert_grid_coords_to_dicts(annotation_data: AnnotationCreate) -> tuple[dict | None, dict | None]:
    """Convert Point models to dicts for JSON serialization.

    Returns (upper_left_dict, lower_right_dict) tuple.
    """
    upper_left = annotation_data.grid_upper_left.model_dump() if annotation_data.grid_upper_left else None
    lower_right = annotation_data.grid_lower_right.model_dump() if annotation_data.grid_lower_right else None
    return upper_left, lower_right


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/annotations", tags=["Annotations"])


@router.post("/", response_model=AnnotationRead, status_code=status.HTTP_201_CREATED)
async def create_or_update_annotation(
    annotation_data: AnnotationCreate,
    db: DatabaseSession,
    current_user: CurrentUser,
    repo: AnnotationRepo,
    screenshot_repo: ScreenshotRepo,
):
    """
    Create or update an annotation (upsert).
    If user already has an annotation for this screenshot, update it.
    Otherwise, create a new one.
    """
    # Use row lock to prevent race condition when incrementing annotation count
    screenshot = await get_screenshot_for_update(screenshot_repo, annotation_data.screenshot_id)

    # Check for existing annotation by this user for this screenshot
    existing = await repo.get_by_user_and_screenshot(current_user.id, annotation_data.screenshot_id)

    try:
        if existing:
            # UPDATE existing annotation
            logger.info(
                "User updating annotation",
                extra={"username": current_user.username, "annotation_id": existing.id, "screenshot_id": screenshot.id},
            )
            # Capture old values for audit log
            old_values = annotation_to_dict(existing)

            grid_upper_left_dict, grid_lower_right_dict = convert_grid_coords_to_dicts(annotation_data)

            existing.hourly_values = annotation_data.hourly_values
            existing.extracted_title = annotation_data.extracted_title
            existing.extracted_total = annotation_data.extracted_total
            existing.grid_upper_left = grid_upper_left_dict
            existing.grid_lower_right = grid_lower_right_dict
            existing.time_spent_seconds = annotation_data.time_spent_seconds
            existing.notes = annotation_data.notes
            existing.status = SubmissionStatus.SUBMITTED.value

            # Create audit log for update
            new_values = annotation_to_dict(existing)
            await create_audit_log(
                db,
                annotation_id=existing.id,
                screenshot_id=screenshot.id,
                user_id=current_user.id,
                action="updated",
                previous_values=old_values,
                new_values=new_values,
            )

            await db.commit()
            await db.refresh(existing)
            invalidate_stats_and_groups()

            # Re-analyze consensus if needed (non-fatal — annotation is already saved)
            if screenshot.current_annotation_count >= 2:
                try:
                    await ConsensusService.analyze_consensus(db, screenshot.id)
                except Exception as consensus_err:
                    logger.warning(
                        "Consensus analysis failed after annotation update",
                        extra={"screenshot_id": screenshot.id, "error": str(consensus_err)},
                    )

            return AnnotationRead.model_validate(existing)
        else:
            # CREATE new annotation
            logger.info(
                "User creating annotation", extra={"username": current_user.username, "screenshot_id": screenshot.id}
            )
            grid_upper_left_dict, grid_lower_right_dict = convert_grid_coords_to_dicts(annotation_data)

            new_annotation = Annotation(
                screenshot_id=annotation_data.screenshot_id,
                user_id=current_user.id,
                hourly_values=annotation_data.hourly_values,
                extracted_title=annotation_data.extracted_title,
                extracted_total=annotation_data.extracted_total,
                grid_upper_left=grid_upper_left_dict,
                grid_lower_right=grid_lower_right_dict,
                time_spent_seconds=annotation_data.time_spent_seconds,
                notes=annotation_data.notes,
                status=SubmissionStatus.SUBMITTED.value,
            )

            db.add(new_annotation)

            # Just track annotation count - do NOT change screenshot status
            # Screenshots are filtered by tags, not removed from queues
            screenshot.current_annotation_count += 1

            # Flush to get annotation ID without committing
            await db.flush()

            # Create audit log (now has annotation ID from flush)
            new_values = annotation_to_dict(new_annotation)
            await create_audit_log(
                db,
                annotation_id=new_annotation.id,
                screenshot_id=screenshot.id,
                user_id=current_user.id,
                action="created",
                new_values=new_values,
            )

            # Single atomic commit for annotation + audit log
            await db.commit()
            await db.refresh(new_annotation)
            invalidate_stats_and_groups()

            logger.info(
                "Annotation created",
                extra={
                    "annotation_id": new_annotation.id,
                    "username": current_user.username,
                    "screenshot_id": screenshot.id,
                    "annotation_count": screenshot.current_annotation_count,
                },
            )

            # Analyze consensus (non-fatal — annotation is already saved)
            if screenshot.current_annotation_count >= 2:
                try:
                    await ConsensusService.analyze_consensus(db, screenshot.id)
                except Exception as consensus_err:
                    logger.warning(
                        "Consensus analysis failed after annotation create",
                        extra={"screenshot_id": screenshot.id, "error": str(consensus_err)},
                    )

            return AnnotationRead.model_validate(new_annotation)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            "Failed to save annotation", extra={"screenshot_id": annotation_data.screenshot_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save annotation",
        )


@router.get("/history", response_model=list[AnnotationWithIssues])
async def get_user_annotation_history(
    repo: AnnotationRepo,
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    annotations = await repo.list_by_user(current_user.id, skip, limit)

    # Issues already loaded via selectinload - no additional queries needed
    return [
        AnnotationWithIssues(
            **AnnotationRead.model_validate(annotation).model_dump(),
            issues=[ProcessingIssueRead.model_validate(issue) for issue in annotation.issues],
        )
        for annotation in annotations
    ]


@router.get("/{annotation_id}", response_model=AnnotationWithIssues)
async def get_annotation(annotation_id: int, repo: AnnotationRepo, current_user: CurrentUser):
    annotation = await repo.get_by_id_with_issues(annotation_id)

    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    if annotation.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this annotation",
        )

    return AnnotationWithIssues(
        **AnnotationRead.model_validate(annotation).model_dump(),
        issues=[ProcessingIssueRead.model_validate(issue) for issue in annotation.issues],
    )


@router.put("/{annotation_id}", response_model=AnnotationRead)
async def update_annotation(
    annotation_id: int,
    annotation_data: AnnotationUpdate,
    db: DatabaseSession,
    current_user: CurrentUser,
    repo: AnnotationRepo,
    screenshot_repo: ScreenshotRepo,
):
    # Use row lock to prevent lost updates from concurrent requests
    annotation = await repo.get_by_id_for_update(annotation_id)

    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    if annotation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own annotations",
        )

    try:
        update_data = annotation_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(annotation, field, value)

        await db.commit()
        await db.refresh(annotation)
        invalidate_stats_and_groups()

        logger.info(
            "User updated annotation", extra={"username": current_user.username, "annotation_id": annotation_id}
        )

        # Re-analyze consensus (non-fatal — annotation update is already saved)
        if annotation.screenshot_id:
            # Lock must succeed — let it propagate if it fails
            await get_screenshot_for_update(screenshot_repo, annotation.screenshot_id)
            try:
                await ConsensusService.analyze_consensus(db, annotation.screenshot_id)
            except Exception as consensus_err:
                logger.warning(
                    "Consensus analysis failed after annotation update",
                    extra={"screenshot_id": annotation.screenshot_id, "error": str(consensus_err)},
                )

        return AnnotationRead.model_validate(annotation)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to update annotation", extra={"annotation_id": annotation_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update annotation",
        )


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: int,
    db: DatabaseSession,
    current_user: CurrentUser,
    repo: AnnotationRepo,
    screenshot_repo: ScreenshotRepo,
):
    annotation = await repo.get_by_id(annotation_id)

    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    if annotation.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own annotations",
        )

    screenshot_id = annotation.screenshot_id
    annotation_id_for_log = annotation.id  # Save before deletion

    # Capture values for audit log before deletion
    old_values = annotation_to_dict(annotation)

    try:
        # Use row lock to prevent race condition when decrementing annotation count
        screenshot = await get_screenshot_for_update(screenshot_repo, screenshot_id)

        # Create audit log BEFORE deleting (to capture annotation reference)
        await create_audit_log(
            db,
            annotation_id=annotation_id_for_log,
            screenshot_id=screenshot_id,
            user_id=current_user.id,
            action="deleted",
            previous_values=old_values,
        )

        await db.delete(annotation)

        screenshot.current_annotation_count = max(0, screenshot.current_annotation_count - 1)

        if screenshot.current_annotation_count < screenshot.target_annotations:
            screenshot.annotation_status = AnnotationStatus.PENDING

        await db.commit()
        invalidate_stats_and_groups()

        logger.info(
            "User deleted annotation",
            extra={"username": current_user.username, "annotation_id": annotation_id, "screenshot_id": screenshot_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Failed to delete annotation", extra={"annotation_id": annotation_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete annotation",
        )
