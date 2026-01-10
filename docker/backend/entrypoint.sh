#!/bin/bash
set -e

echo "=== Backend Startup ==="

# Convert async URL to sync for alembic
export SYNC_DATABASE_URL="${DATABASE_URL//+asyncpg/+psycopg2}"

# Check database state and determine what to do
MIGRATION_ACTION=$(python -c "
from sqlalchemy import create_engine, text
import os

engine = create_engine(os.environ['SYNC_DATABASE_URL'])
with engine.connect() as conn:
    # Check if users table exists (indicates existing DB)
    has_tables = conn.execute(text(
        \"SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='users')\"
    )).scalar()

    # Check if processing_started_at column exists
    has_new_column = conn.execute(text(
        \"SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='screenshots' AND column_name='processing_started_at')\"
    )).scalar()

    # Check if alembic_version table exists and has rows
    try:
        version = conn.execute(text('SELECT version_num FROM alembic_version')).scalar()
    except:
        version = None

    if not has_tables:
        # Fresh database - run all migrations
        print('fresh')
    elif version == 'i7j8k9l0m1n2' and not has_new_column:
        # BAD STATE: Stamped to new migration but column doesn't exist
        # Fix by resetting to previous and running upgrade
        print('fix_bad_stamp')
    elif version is None:
        # Existing DB without alembic tracking - stamp to PREVIOUS head then upgrade
        print('stamp_previous')
    else:
        # Normal case - alembic is tracking, just upgrade
        print('upgrade')
")

echo "Migration action: $MIGRATION_ACTION"

if [ "$MIGRATION_ACTION" = "fresh" ]; then
    echo "Fresh database - running all migrations..."
    alembic upgrade head
elif [ "$MIGRATION_ACTION" = "fix_bad_stamp" ]; then
    echo "Fixing bad stamp state - resetting to 1dc90afb6cac and upgrading..."
    alembic stamp 1dc90afb6cac
    alembic upgrade head
elif [ "$MIGRATION_ACTION" = "stamp_previous" ]; then
    echo "Existing database without alembic tracking - stamping to 1dc90afb6cac then upgrading..."
    alembic stamp 1dc90afb6cac
    alembic upgrade head
else
    echo "Running database migrations..."
    alembic upgrade head
fi

echo "Starting uvicorn..."
exec uvicorn src.screenshot_processor.web.api.main:app --host 0.0.0.0 --port 8000
