#!/bin/bash
set -euo pipefail

# =============================================================================
# PostgreSQL Backup Script — ios-screen-time-screenshot-processing (unified)
# =============================================================================
# Usage:
#   ./scripts/backup-db.sh              # Full backup
#   ./scripts/backup-db.sh --db-only    # Database only (skip uploads)
#   ./scripts/backup-db.sh --dry-run    # Show what would happen
# =============================================================================

# --- Configuration ---
BACKUP_ROOT="/home/YOUR_USER/backups/ios-screen-time"

# Auto-detect container name: try production first, then dev
PG_CONTAINER="ios-screen-time-screenshot-processing-postgres"
if ! docker inspect --format='{{.State.Status}}' "$PG_CONTAINER" 2>/dev/null | grep -q running; then
    PG_CONTAINER="ios-screen-time-screenshot-processing-postgres-dev"
fi

BACKEND_CONTAINER="ios-screen-time-screenshot-processing-backend"
if ! docker inspect --format='{{.State.Status}}' "$BACKEND_CONTAINER" 2>/dev/null | grep -q running; then
    BACKEND_CONTAINER="ios-screen-time-screenshot-processing-backend-dev"
fi
# ---------------------

RETENTION_DAYS=14
WAL_RETENTION_DAYS=2
BASEBACKUP_KEEP=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

DB_BACKUP_DIR="$BACKUP_ROOT/db"
UPLOADS_BACKUP_DIR="$BACKUP_ROOT/uploads"
BASEBACKUP_DIR="$BACKUP_ROOT/basebackup"
LOG_FILE="$BACKUP_ROOT/logs/backup.log"

DB_ONLY=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --db-only)   DB_ONLY=true ;;
        --dry-run)   DRY_RUN=true ;;
        -h|--help)   head -8 "$0" | tail -6; exit 0 ;;
    esac
done

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

die() { log "FATAL: $1"; exit 1; }

mkdir -p "$DB_BACKUP_DIR" "$UPLOADS_BACKUP_DIR" "$BASEBACKUP_DIR" "$(dirname "$LOG_FILE")"

log "=== Backup starting ==="

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
if ! docker inspect --format='{{.State.Status}}' "$PG_CONTAINER" 2>/dev/null | grep -q running; then
    die "Container '$PG_CONTAINER' is not running."
fi

DB_USER=$(docker exec "$PG_CONTAINER" sh -c 'echo $POSTGRES_USER' 2>/dev/null)
DB_NAME=$(docker exec "$PG_CONTAINER" sh -c 'echo $POSTGRES_DB' 2>/dev/null)
[ -z "$DB_USER" ] || [ -z "$DB_NAME" ] && die "Could not detect DB credentials from container"

docker exec "$PG_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" -q 2>/dev/null \
    || die "PostgreSQL not accepting connections"

if $DRY_RUN; then
    log "[DRY RUN] Would create: $DB_BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"
    log "[DRY RUN] Would create: $DB_BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"
    if ! $DB_ONLY; then
        log "[DRY RUN] Would sync uploads to: $UPLOADS_BACKUP_DIR/"
    fi
    log "[DRY RUN] Would run base backup if none exists from today"
    log "[DRY RUN] Retention: dumps=${RETENTION_DAYS}d, WAL=${WAL_RETENTION_DAYS}d, base=${BASEBACKUP_KEEP}"
    exit 0
fi

# -----------------------------------------------------------------------------
# 1. Database dump — custom format (fast restore, compressed)
# -----------------------------------------------------------------------------
DUMP_FILE="$DB_BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"
log "Dumping (custom format) → $DUMP_FILE"
docker exec "$PG_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom > "$DUMP_FILE" \
    || die "pg_dump (custom) failed"
log "Custom dump: $(du -h "$DUMP_FILE" | cut -f1)"

# -----------------------------------------------------------------------------
# 2. Database dump — SQL (portable, human-readable)
# -----------------------------------------------------------------------------
SQL_GZ="$DB_BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"
log "Dumping (SQL + gzip) → $SQL_GZ"
docker exec "$PG_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --format=plain | gzip -9 > "$SQL_GZ" \
    || die "pg_dump (SQL) failed"
log "SQL dump: $(du -h "$SQL_GZ" | cut -f1)"

# -----------------------------------------------------------------------------
# 3. Backup uploads (if backend container specified and running)
# -----------------------------------------------------------------------------
if ! $DB_ONLY; then
    if docker inspect --format='{{.State.Status}}' "$BACKEND_CONTAINER" 2>/dev/null | grep -q running; then
        log "Syncing uploads → $UPLOADS_BACKUP_DIR/"
        docker exec "$BACKEND_CONTAINER" tar cf - -C /app/uploads . 2>/dev/null \
            | tar xf - -C "$UPLOADS_BACKUP_DIR/" 2>/dev/null \
            || log "WARNING: Upload backup had issues (may be empty)"
        log "Uploads: $(find "$UPLOADS_BACKUP_DIR" -type f 2>/dev/null | wc -l) files"
    else
        log "WARNING: Backend container not running, skipping uploads"
    fi
fi

# -----------------------------------------------------------------------------
# 4. Base backup for PITR (daily — skip if today's already exists)
# -----------------------------------------------------------------------------
LATEST_BASE=$(find "$BASEBACKUP_DIR" -name "base_*.tar.gz" -mtime -1 2>/dev/null | head -1)

if [ -z "$LATEST_BASE" ]; then
    BASE_FILE="$BASEBACKUP_DIR/base_${TIMESTAMP}.tar.gz"
    log "Taking base backup (for PITR) → $BASE_FILE"
    docker exec "$PG_CONTAINER" pg_basebackup -U "$DB_USER" -D /tmp/basebackup -Ft -z -P 2>/dev/null \
        && docker cp "$PG_CONTAINER":/tmp/basebackup/base.tar.gz "$BASE_FILE" \
        && docker exec "$PG_CONTAINER" rm -rf /tmp/basebackup \
        && log "Base backup: $(du -h "$BASE_FILE" | cut -f1)" \
        || log "WARNING: Base backup failed"
    # Prune old base backups
    find "$BASEBACKUP_DIR" -name "base_*.tar.gz" -type f | sort | head -n -${BASEBACKUP_KEEP} | xargs rm -f 2>/dev/null
else
    log "Skipping base backup (latest: $(basename "$LATEST_BASE"))"
fi

# -----------------------------------------------------------------------------
# 5. WAL archive cleanup (if archive_mode is on)
# -----------------------------------------------------------------------------
ARCHIVE_MODE=$(docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SHOW archive_mode;" 2>/dev/null | tr -d ' ')

if [ "$ARCHIVE_MODE" = "on" ]; then
    log "WAL archive_mode=on — cleaning old WAL files (>${WAL_RETENTION_DAYS} days)..."

    WAL_BACKUP_DIR="$BACKUP_ROOT/wal"
    if [ -d "$WAL_BACKUP_DIR" ]; then
        DELETED_WALS=$(find "$WAL_BACKUP_DIR" -name "0*" -mtime +$WAL_RETENTION_DAYS -delete -print 2>/dev/null | wc -l)
        log "Cleaned host WAL: $DELETED_WALS files"
    fi

    for WAL_VOL in $(docker volume ls --format '{{.Name}}' | grep "wal_archive" 2>/dev/null); do
        docker run --rm -v "$WAL_VOL":/wal alpine sh -c \
            "find /wal -name '0*' -mtime +$WAL_RETENTION_DAYS -delete 2>/dev/null" || true
        log "Cleaned Docker volume WAL: $WAL_VOL"
    done

    for BIND_WAL in /opt/*/backups/wal; do
        if [ -d "$BIND_WAL" ]; then
            DELETED_BIND=$(find "$BIND_WAL" -name "0*" -mtime +$WAL_RETENTION_DAYS -delete -print 2>/dev/null | wc -l)
            [ "$DELETED_BIND" -gt 0 ] && log "Cleaned bind-mount WAL ($BIND_WAL): $DELETED_BIND files"
        fi
    done
else
    log "WAL archive_mode=off — no WAL cleanup needed"
fi

# -----------------------------------------------------------------------------
# 6. Retention — delete old dumps
# -----------------------------------------------------------------------------
log "Cleaning dumps older than $RETENTION_DAYS days..."
DELETED_DUMPS=$(find "$DB_BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete -print | wc -l)
DELETED_SQLS=$(find "$DB_BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
log "Cleaned: $DELETED_DUMPS .dump, $DELETED_SQLS .sql.gz"

# -----------------------------------------------------------------------------
# 7. Summary + disk space check
# -----------------------------------------------------------------------------
TOTAL_DUMPS=$(find "$DB_BACKUP_DIR" -name "*.dump" | wc -l)
DUMP_SIZE=$(du -sh "$DB_BACKUP_DIR" | cut -f1)
BASE_COUNT=$(find "$BASEBACKUP_DIR" -name "base_*.tar.gz" 2>/dev/null | wc -l)
BASE_SIZE=$(du -sh "$BASEBACKUP_DIR" 2>/dev/null | cut -f1 || echo "0")

log "=== Backup complete ==="
log "  Dumps: $TOTAL_DUMPS backups, $DUMP_SIZE"
log "  Base backups: $BASE_COUNT, $BASE_SIZE"
log "  Retention: dumps=${RETENTION_DAYS}d, WAL=${WAL_RETENTION_DAYS}d, base=${BASEBACKUP_KEEP}"
log "  Latest: $DUMP_FILE"

DISK_USE_PCT=$(df / --output=pcent | tail -1 | tr -d ' %')
if [ "$DISK_USE_PCT" -gt 80 ]; then
    log "WARNING: Disk usage at ${DISK_USE_PCT}%! Free space: $(df -h / --output=avail | tail -1 | tr -d ' ')"
fi
