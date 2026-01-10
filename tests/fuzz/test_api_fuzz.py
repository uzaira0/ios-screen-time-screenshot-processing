# pyright: reportPossiblyUnboundVariable=false
"""
API fuzz testing using Schemathesis.

Generates random valid/invalid requests based on the OpenAPI schema
and verifies the API handles them without crashing (no 500s).

Skips if schemathesis not installed or app cannot be imported.
"""
import os
import warnings

import pytest

try:
    import schemathesis

    HAS_SCHEMATHESIS = True
except ImportError:
    HAS_SCHEMATHESIS = False

pytestmark = pytest.mark.skipif(not HAS_SCHEMATHESIS, reason="schemathesis not installed")

schema = None
_schema_load_error = None

if HAS_SCHEMATHESIS:
    try:
        os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long-for-testing")
        os.environ.pop("SITE_PASSWORD", None)
        from screenshot_processor.web.api.main import app

        schema = schemathesis.from_asgi("/openapi.json", app=app)
    except Exception as exc:
        _schema_load_error = str(exc)
        warnings.warn(f"[test_api_fuzz] Could not load app schema: {exc}", stacklevel=1)


def test_schema_loaded():
    """Verify the schema was loaded — fail loudly if not."""
    if not HAS_SCHEMATHESIS:
        pytest.skip("schemathesis not installed")
    if schema is None:
        pytest.fail(
            f"Schemathesis schema failed to load. Cannot run fuzz tests. "
            f"Error: {_schema_load_error or 'unknown'}"
        )


if schema is not None:

    @schema.parametrize()
    def test_api_does_not_crash(case):
        """Every API endpoint should handle any valid schema input without 500."""
        case.headers = case.headers or {}
        case.headers["X-Username"] = "fuzz-tester"

        response = case.call_asgi()
        case.validate_response(response)
        assert response.status_code < 500, (
            f"{case.method} {case.path} returned {response.status_code}"
        )
