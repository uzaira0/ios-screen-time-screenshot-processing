# Backup Strategy

This document outlines the backup procedures for the Screenshot Annotation Platform, covering PostgreSQL database, uploaded files, and configuration.

## Overview

| Component | Backup Method | Frequency | Retention |
|-----------|---------------|-----------|-----------|
| PostgreSQL | pg_dump + compression | Daily | 30 days |
| Screenshot files | rsync/rclone | Daily | 90 days |
| Configuration | Git + encrypted secrets | On change | Indefinite |

---

## PostgreSQL Database Backup

### Automated Daily Backups

Create `/usr/local/bin/backup-screenshot-db.sh`:

```bash
#!/bin/bash
set -euo pipefail

# Configuration
BACKUP_DIR="/var/backups/screenshot-db"
DB_NAME="screenshot_annotations"
DB_USER="screenshot"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_$TIMESTAMP.sql"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Perform backup with progress logging
echo "[$(date)] Starting backup of $DB_NAME..."

pg_dump -U "$DB_USER" -h localhost "$DB_NAME" \
    --format=custom \
    --file="$BACKUP_FILE.dump" \
    --verbose 2>&1 | tail -n 5

# Also create SQL backup for portability
pg_dump -U "$DB_USER" -h localhost "$DB_NAME" > "$BACKUP_FILE"

# Compress SQL backup
gzip -9 "$BACKUP_FILE"

# Calculate backup sizes
DUMP_SIZE=$(du -h "$BACKUP_FILE.dump" | cut -f1)
GZ_SIZE=$(du -h "$BACKUP_FILE.gz" | cut -f1)

echo "[$(date)] Backup completed:"
echo "  - Custom format: ${BACKUP_FILE}.dump ($DUMP_SIZE)"
echo "  - SQL compressed: ${BACKUP_FILE}.gz ($GZ_SIZE)"

# Delete old backups
find "$BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete

# Count remaining backups
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "*.dump" | wc -l)
echo "[$(date)] Retention: keeping $BACKUP_COUNT backups ($RETENTION_DAYS day policy)"
```

### Cron Schedule

```bash
# Add to /etc/crontab or via `sudo crontab -e`
# Run daily at 2:00 AM
0 2 * * * /usr/local/bin/backup-screenshot-db.sh >> /var/log/screenshot-backup.log 2>&1
```

### Manual Backup

```bash
# Quick manual backup
pg_dump -U screenshot screenshot_annotations | gzip > backup_$(date +%Y%m%d).sql.gz

# With custom format (faster restore)
pg_dump -U screenshot -Fc screenshot_annotations > backup_$(date +%Y%m%d).dump
```

---

## Screenshot File Backup

Uploaded screenshot images are stored in the `UPLOAD_DIR` (default: `uploads/screenshots`).

### Local Backup with rsync

Create `/usr/local/bin/backup-screenshot-files.sh`:

```bash
#!/bin/bash
set -euo pipefail

SOURCE_DIR="/var/www/screenshot-annotator/uploads/screenshots"
BACKUP_DIR="/var/backups/screenshot-files"
RETENTION_DAYS=90
TIMESTAMP=$(date +%Y%m%d)

# Create dated backup directory
mkdir -p "$BACKUP_DIR/$TIMESTAMP"

# Incremental backup using hard links to previous backup
LATEST=$(ls -td "$BACKUP_DIR"/[0-9]* 2>/dev/null | head -1)

if [ -n "$LATEST" ] && [ "$LATEST" != "$BACKUP_DIR/$TIMESTAMP" ]; then
    # Use hard links to previous backup (saves space)
    rsync -av --link-dest="$LATEST" "$SOURCE_DIR/" "$BACKUP_DIR/$TIMESTAMP/"
else
    # First backup or same day
    rsync -av "$SOURCE_DIR/" "$BACKUP_DIR/$TIMESTAMP/"
fi

echo "[$(date)] File backup completed: $BACKUP_DIR/$TIMESTAMP"

# Delete old backups
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +$RETENTION_DAYS -exec rm -rf {} \;
```

### Remote Backup with rclone

For offsite backups to S3, B2, or other cloud storage:

```bash
# Configure rclone first: rclone config
# Example: create remote named 'backup-s3'

rclone sync /var/backups/screenshot-db backup-s3:screenshot-backups/db/ --progress
rclone sync /var/backups/screenshot-files backup-s3:screenshot-backups/files/ --progress
```

### Docker Volume Backup

When using Docker, back up the mounted volumes:

```bash
# Stop containers first for consistency (optional but recommended)
docker compose -f docker/docker-compose.yml stop

# Backup database volume
docker run --rm \
    -v screenshot-annotator_postgres_data:/data \
    -v /var/backups:/backup \
    alpine tar czf /backup/postgres_data_$(date +%Y%m%d).tar.gz -C /data .

# Backup uploads volume
docker run --rm \
    -v screenshot-annotator_uploads:/data \
    -v /var/backups:/backup \
    alpine tar czf /backup/uploads_$(date +%Y%m%d).tar.gz -C /data .

# Restart containers
docker compose -f docker/docker-compose.yml start
```

---

## Configuration Backup

### Environment Files

**Never commit secrets to Git.** Use encrypted backups:

```bash
# Encrypt .env file with GPG
gpg --symmetric --cipher-algo AES256 -o .env.gpg .env

# Store encrypted file in secure location
cp .env.gpg /var/backups/config/

# Decrypt when needed
gpg --decrypt .env.gpg > .env.restored
```

### What to Back Up

| File | Purpose | Location |
|------|---------|----------|
| `.env` | Backend secrets | Project root |
| `frontend/.env` | Frontend config | `frontend/` |
| `alembic/versions/` | Database migrations | `alembic/versions/` |
| `gunicorn.conf.py` | Production server config | Project root |
| `nginx/*.conf` | Web server config | `/etc/nginx/sites-available/` |
| `systemd/*.service` | Service definitions | `/etc/systemd/system/` |

---

## Restore Procedures

### Restore PostgreSQL Database

```bash
# From custom format (recommended - faster)
pg_restore -U screenshot -d screenshot_annotations --clean backup.dump

# From SQL file
gunzip -c backup.sql.gz | psql -U screenshot screenshot_annotations

# If database doesn't exist
createdb -U screenshot screenshot_annotations
pg_restore -U screenshot -d screenshot_annotations backup.dump
```

### Restore Screenshot Files

```bash
# From rsync backup
rsync -av /var/backups/screenshot-files/20241227/ /var/www/screenshot-annotator/uploads/screenshots/

# From tar archive
tar xzf uploads_20241227.tar.gz -C /var/www/screenshot-annotator/uploads/screenshots/
```

### Full Disaster Recovery

1. **Provision new server** with same OS and dependencies
2. **Restore configuration**:
   ```bash
   gpg --decrypt .env.gpg > .env
   ```
3. **Restore database**:
   ```bash
   createdb screenshot_annotations
   pg_restore -d screenshot_annotations latest_backup.dump
   ```
4. **Restore files**:
   ```bash
   rsync -av backup-server:/var/backups/screenshot-files/latest/ uploads/screenshots/
   ```
5. **Run migrations** (if any pending):
   ```bash
   alembic upgrade head
   ```
6. **Start services**:
   ```bash
   sudo systemctl start screenshot-api
   ```
7. **Verify**:
   - Check health endpoint: `curl http://localhost:8000/health`
   - Test login and annotation flow

---

## Backup Verification

### Weekly Backup Test (Automated)

Create `/usr/local/bin/verify-backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/var/backups/screenshot-db"
TEST_DB="screenshot_test_restore"

# Find latest backup
LATEST=$(ls -t "$BACKUP_DIR"/*.dump 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    echo "ERROR: No backup found"
    exit 1
fi

echo "[$(date)] Testing restore of: $LATEST"

# Drop and recreate test database
dropdb --if-exists "$TEST_DB"
createdb "$TEST_DB"

# Attempt restore
if pg_restore -d "$TEST_DB" "$LATEST" 2>&1; then
    # Verify data integrity
    SCREENSHOT_COUNT=$(psql -t -c "SELECT COUNT(*) FROM screenshots" "$TEST_DB" | tr -d ' ')
    ANNOTATION_COUNT=$(psql -t -c "SELECT COUNT(*) FROM annotations" "$TEST_DB" | tr -d ' ')

    echo "[$(date)] Restore successful!"
    echo "  - Screenshots: $SCREENSHOT_COUNT"
    echo "  - Annotations: $ANNOTATION_COUNT"

    # Cleanup
    dropdb "$TEST_DB"
    exit 0
else
    echo "ERROR: Restore failed!"
    exit 1
fi
```

### Cron for Weekly Verification

```bash
# Run every Sunday at 4:00 AM
0 4 * * 0 /usr/local/bin/verify-backup.sh >> /var/log/backup-verify.log 2>&1
```

---

## Monitoring & Alerts

### Check Backup Age

```bash
#!/bin/bash
# Alert if no backup in last 48 hours
LATEST=$(ls -t /var/backups/screenshot-db/*.dump 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
    echo "CRITICAL: No backups found!"
    exit 2
fi

AGE_HOURS=$(( ($(date +%s) - $(stat -c %Y "$LATEST")) / 3600 ))
if [ $AGE_HOURS -gt 48 ]; then
    echo "WARNING: Latest backup is $AGE_HOURS hours old"
    exit 1
fi

echo "OK: Latest backup is $AGE_HOURS hours old"
exit 0
```

### Disk Space Monitoring

```bash
# Alert if backup directory > 80% capacity
USAGE=$(df /var/backups | tail -1 | awk '{print $5}' | tr -d '%')
if [ $USAGE -gt 80 ]; then
    echo "WARNING: Backup disk at ${USAGE}% capacity"
fi
```

---

## Backup Checklist

- [ ] Daily PostgreSQL backups configured
- [ ] Daily file backups configured
- [ ] Retention policies set (30 days DB, 90 days files)
- [ ] Offsite/cloud backup enabled
- [ ] Weekly restore verification running
- [ ] Monitoring/alerts configured
- [ ] Disaster recovery procedure documented
- [ ] .env files encrypted and backed up
- [ ] Backup scripts tested manually
- [ ] Restore procedure tested on separate system
