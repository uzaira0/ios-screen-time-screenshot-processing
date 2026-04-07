"""
Vulture whitelist — functions that appear unused but are used dynamically.

Vulture can't detect usage through:
- FastAPI dependency injection (Depends())
- SQLAlchemy event listeners
- Alembic migration functions
- pytest fixtures
- CLI entry points
"""
# Alembic migrations
upgrade  # noqa
downgrade  # noqa

# FastAPI dependency injection
get_db  # noqa
get_current_user  # noqa
require_admin  # noqa

# pytest fixtures
db_session  # noqa
client  # noqa
test_user  # noqa
test_admin  # noqa
test_group  # noqa
test_screenshot  # noqa
multiple_users  # noqa
multiple_screenshots  # noqa
event_loop  # noqa
