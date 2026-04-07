"""
Test that all backend imports work correctly.
"""

from __future__ import annotations


class TestDatabaseModels:
    """Test database model imports."""

    def test_import_models(self):
        """Test that database models can be imported."""
        from screenshot_processor.web.database.models import (
            Annotation,
            Screenshot,
            User,
        )

        assert User is not None
        assert Screenshot is not None
        assert Annotation is not None


class TestSchemas:
    """Test Pydantic schema imports."""

    def test_import_schemas(self):
        """Test that Pydantic schemas can be imported."""
        from screenshot_processor.web.database.schemas import (
            ScreenshotRead,
            UserCreate,
        )

        assert UserCreate is not None
        assert ScreenshotRead is not None


class TestServices:
    """Test service imports."""

    def test_import_services(self):
        """Test that services can be imported."""
        from screenshot_processor.web.services import (
            ConsensusService,
            QueueService,
        )

        assert QueueService is not None
        assert ConsensusService is not None


class TestFastAPIApp:
    """Test FastAPI app imports."""

    def test_import_app(self):
        """Test that FastAPI app can be imported."""
        from screenshot_processor.web.api.main import app

        assert app is not None
