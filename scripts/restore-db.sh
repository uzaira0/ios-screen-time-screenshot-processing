#!/bin/bash
# =============================================================================
# PostgreSQL Restore Script — ios-screen-time-screenshot-processing
# =============================================================================
# Restores a database backup into the Docker PostgreSQL container.
#
# Usage:
#   ./scripts/restore-db.sh                              # Restore latest backup
#   ./scripts/restore-db.sh /path/to/backup.dump         # Restore specific .dump
#   ./scripts/restore-db.sh /path/to/backup.sql.gz       # Restore specific .sql.gz
#   ./scripts/restore-db.sh --list                       # List available backups
#
# The script will:
#   1. Verify the container is running
#   2. Show backup info and ask for confirmation
#   3. Drop and recreate the database
#   4. Restore from the backup file
#   5. Run alembic upgrade head (if needed)
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BACKUP_DIR="/home/YOUR_USER/backups/ios-screen-time/db"
UPLOADS_BACKUP_DIR="/home/YOUR_USER/backups/ios-screen-time/uploads"

# Auto-detect container name: try production name first, then dev
CONTAINER_NAME="ios-screen-time-screenshot-processing-postgres"
if ! docker inspect --format='{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null | grep -q running; then
    CONTAINER_NAME="ios-screen-time-screenshot-processing-postgres-dev"
fi
BACKEND_CONTAINER="ios-screen-time-screenshot-processing-backend"
if ! docker inspect --format='{{.State.Status}}' "$BACKEND_CONTAINER" 2>/dev/null | grep -q running; then
    BACKEND_CONTAINER="ios-screen-time-screenshot-processing-backend-dev"
fi

# Auto-detect credentials from the running container (Dokploy may override .env values)
DB_USER=$(docker exec "$CONTAINER_NAME" bash -c 'echo $POSTGRES_USER' 2>/dev/null || echo "screenshot")
DB_NAME=$(docker exec "$CONTAINER_NAME" bash -c 'echo $POSTGRES_DB' 2>/dev/null || echo "screenshot_annotations")
PG_ADMIN_USER="$DB_USER"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }
die() { log "FATAL: $1"; exit 1; }

list_backups() {
    echo "Available backups in $BACKUP_DIR:"
    echo ""
    if [ -d "$BACKUP_DIR" ]; then
        ls -lht "$BACKUP_DIR"/*.dump 2>/dev/null | awk '{print "  " $NF " (" $5 ", " $6 " " $7 " " $8 ")"}'
        TOTAL=$(ls "$BACKUP_DIR"/*.dump 2>/dev/null | wc -l)
        echo ""
        echo "Total: $TOTAL backups"
    else
        echo "  (no backups found)"
    fi
}

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
if [ "${1:-}" = "--list" ] || [ "${1:-}" = "-l" ]; then
    list_backups
    exit 0
fi

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    head -14 "$0" | tail -12
    exit 0
fi

# Determine backup file to restore
BACKUP_FILE="${1:-}"
if [ -z "$BACKUP_FILE" ]; then
    # Find the latest .dump file
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/*.dump 2>/dev/null | head -1)
    if [ -z "$BACKUP_FILE" ]; then
        die "No backup file specified and no .dump files found in $BACKUP_DIR"
    fi
    log "No file specified, using latest: $BACKUP_FILE"
fi

if [ ! -f "$BACKUP_FILE" ]; then
    die "Backup file not found: $BACKUP_FILE"
fi

# Detect format
IS_SQL_GZ=false
if [[ "$BACKUP_FILE" == *.sql.gz ]]; then
    IS_SQL_GZ=true
fi

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
if ! docker inspect --format='{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null | grep -q running; then
    die "Container '$CONTAINER_NAME' is not running."
fi

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log "Restore plan:"
log "  Source: $BACKUP_FILE ($BACKUP_SIZE)"
log "  Target: $CONTAINER_NAME → $DB_NAME"
echo ""

# Confirmation
read -p "This will DROP and recreate the '$DB_NAME' database. Continue? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log "Aborted."
    exit 1
fi

# -----------------------------------------------------------------------------
# 1. Terminate active connections and drop/recreate the database
# -----------------------------------------------------------------------------
log "Terminating active connections to $DB_NAME..."
docker exec "$CONTAINER_NAME" psql -U "$PG_ADMIN_USER" -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" \
    > /dev/null 2>&1 || true

log "Dropping and recreating database $DB_NAME..."
docker exec "$CONTAINER_NAME" psql -U "$PG_ADMIN_USER" -c "DROP DATABASE IF EXISTS \"$DB_NAME\";"
docker exec "$CONTAINER_NAME" psql -U "$PG_ADMIN_USER" -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";"

# -----------------------------------------------------------------------------
# 2. Restore the backup
# -----------------------------------------------------------------------------
if $IS_SQL_GZ; then
    log "Restoring from SQL backup (gzipped)..."
    gunzip -c "$BACKUP_FILE" \
        | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" \
        > /dev/null 2>&1 \
        || die "SQL restore failed"
else
    log "Restoring from custom-format dump..."
    cat "$BACKUP_FILE" \
        | docker exec -i "$CONTAINER_NAME" pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --no-privileges \
        2>&1 | grep -v "WARNING:" || true
    # pg_restore returns non-zero on warnings, check if tables exist
    TABLE_COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')
    if [ "$TABLE_COUNT" -lt 1 ]; then
        die "Restore appears to have failed — no tables found"
    fi
fi

# -----------------------------------------------------------------------------
# 3. Verify restore
# -----------------------------------------------------------------------------
log "Verifying restore..."

COUNTS=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "
    SELECT 'screenshots: ' || COUNT(*) FROM screenshots
    UNION ALL SELECT 'annotations: ' || COUNT(*) FROM annotations
    UNION ALL SELECT 'users: ' || COUNT(*) FROM users
    UNION ALL SELECT 'groups: ' || COUNT(*) FROM groups;
")

log "Restore verification:"
echo "$COUNTS" | while read -r line; do
    [ -n "$line" ] && log "  $line"
done

# -----------------------------------------------------------------------------
# 4. Optionally restore uploaded files
# -----------------------------------------------------------------------------
if [ -d "$UPLOADS_BACKUP_DIR" ]; then
    UPLOAD_FILE_COUNT=$(find "$UPLOADS_BACKUP_DIR" -type f 2>/dev/null | wc -l)
    if [ "$UPLOAD_FILE_COUNT" -gt 0 ]; then
        echo ""
        read -p "Restore $UPLOAD_FILE_COUNT uploaded files too? [y/N] " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log "Restoring uploaded files..."
            if docker inspect --format='{{.State.Status}}' "$BACKEND_CONTAINER" 2>/dev/null | grep -q running; then
                tar cf - -C "$UPLOADS_BACKUP_DIR" . \
                    | docker exec -i "$BACKEND_CONTAINER" tar xf - -C /app/uploads/
                log "Uploaded files restored."
            else
                log "WARNING: Backend container not running. Files saved at: $UPLOADS_BACKUP_DIR"
            fi
        fi
    fi
fi

# -----------------------------------------------------------------------------
# 5. Restart backend to pick up restored data
# -----------------------------------------------------------------------------
echo ""
read -p "Restart backend containers to pick up the restored data? [Y/n] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    log "Restarting backend..."
    docker restart "$BACKEND_CONTAINER" ios-screen-time-screenshot-processing-celery 2>/dev/null || true
    log "Backend restarted."
fi

log "=== Restore complete ==="
