"""Repository layer for database access.

The repository pattern provides an abstraction over data access logic,
separating query construction from route handlers.

Usage with FastAPI DI:
    from screenshot_processor.web.repositories import AnnotationRepo, ScreenshotRepo

    @router.get("/annotations/{id}")
    async def get_annotation(id: int, repo: AnnotationRepo):
        return await repo.get_by_id(id)
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database import get_db

from .admin_repository import AdminRepository
from .annotation_repository import AnnotationRepository
from .consensus_repository import ConsensusRepository
from .queue_repository import QueueRepository
from .screenshot_repository import NavigationResult, ScreenshotRepository

# =============================================================================
# Dependency Injection Factories
# =============================================================================


def get_screenshot_repo(
    db: AsyncSession = Depends(get_db),
) -> ScreenshotRepository:
    """FastAPI dependency for ScreenshotRepository."""
    return ScreenshotRepository(db)


def get_annotation_repo(
    db: AsyncSession = Depends(get_db),
) -> AnnotationRepository:
    """FastAPI dependency for AnnotationRepository."""
    return AnnotationRepository(db)


def get_consensus_repo(
    db: AsyncSession = Depends(get_db),
) -> ConsensusRepository:
    """FastAPI dependency for ConsensusRepository."""
    return ConsensusRepository(db)


def get_admin_repo(
    db: AsyncSession = Depends(get_db),
) -> AdminRepository:
    """FastAPI dependency for AdminRepository."""
    return AdminRepository(db)


def get_queue_repo(
    db: AsyncSession = Depends(get_db),
) -> QueueRepository:
    """FastAPI dependency for QueueRepository."""
    return QueueRepository(db)


# =============================================================================
# Type Aliases for Route Parameters
# =============================================================================

ScreenshotRepo = Annotated[ScreenshotRepository, Depends(get_screenshot_repo)]
AnnotationRepo = Annotated[AnnotationRepository, Depends(get_annotation_repo)]
ConsensusRepo = Annotated[ConsensusRepository, Depends(get_consensus_repo)]
AdminRepo = Annotated[AdminRepository, Depends(get_admin_repo)]
QueueRepo = Annotated[QueueRepository, Depends(get_queue_repo)]


__all__ = [
    # Repository classes
    "ScreenshotRepository",
    "AnnotationRepository",
    "ConsensusRepository",
    "AdminRepository",
    "QueueRepository",
    # Dataclasses
    "NavigationResult",
    # DI factories
    "get_screenshot_repo",
    "get_annotation_repo",
    "get_consensus_repo",
    "get_admin_repo",
    "get_queue_repo",
    # Type aliases for route parameters
    "ScreenshotRepo",
    "AnnotationRepo",
    "ConsensusRepo",
    "AdminRepo",
    "QueueRepo",
]
