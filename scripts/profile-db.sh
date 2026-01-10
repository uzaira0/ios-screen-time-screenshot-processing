#!/usr/bin/env bash
# =============================================================================
# Database Profiling Script
# =============================================================================
# Queries pg_stat_statements, pg_stat_user_tables, and pg_stat_user_indexes
# to identify slow queries, missing indexes, and unused indexes.
#
# Usage:
#   scripts/profile-db.sh [output-dir]
#
# Requires: PostgreSQL running (docker-compose.dev.yml)
# Uses Docker exec when psql is not available on host.
# =============================================================================
set -euo pipefail

OUT_DIR="${1:-profiling-reports/db}"
mkdir -p "$OUT_DIR"

# Database connection params (match docker-compose.dev.yml)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5436}"
DB_USER="${DB_USER:-ios_screen_time_screenshot}"
DB_NAME="${DB_NAME:-ios_screen_time_screenshot_processing}"
DB_PASSWORD="${POSTGRES_PASSWORD:-ios_screen_time_screenshot}"

# Use Docker exec if psql is not available on host
if command -v psql &>/dev/null; then
    run_psql() {
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" "$@"
    }
else
    PG_CONTAINER="${PG_CONTAINER:-ios-screen-time-screenshot-processing-postgres-dev}"
    run_psql() {
        docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" "$@"
    }
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail() { echo -e "${RED}✗${NC} $1"; }

echo "=== Database Profiling Report ===" > "$OUT_DIR/db-profile.txt"
echo "Generated: $(date)" >> "$OUT_DIR/db-profile.txt"
echo "" >> "$OUT_DIR/db-profile.txt"

# --- Check pg_stat_statements availability ---
echo "Checking pg_stat_statements..."
PG_STAT_AVAILABLE=$(run_psql -t -A \
    -c "SELECT COUNT(*) FROM pg_available_extensions WHERE name='pg_stat_statements';" 2>/dev/null || echo "0")

if [ "$PG_STAT_AVAILABLE" = "1" ]; then
    # Try to create extension if not exists
    run_psql -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;" 2>/dev/null || true

    # Top 20 slowest queries by total time
    echo "=== Top 20 Slowest Queries (by total time) ===" >> "$OUT_DIR/db-profile.txt"
    run_psql -c "
SELECT
    round(total_exec_time::numeric, 2) AS total_ms,
    calls,
    round(mean_exec_time::numeric, 2) AS mean_ms,
    round(max_exec_time::numeric, 2) AS max_ms,
    rows,
    LEFT(query, 120) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 20;
" >> "$OUT_DIR/db-profile.txt" 2>/dev/null \
    && log_ok "Slow queries report saved" \
    || log_warn "pg_stat_statements query failed (extension may not be loaded)"

    echo "" >> "$OUT_DIR/db-profile.txt"

    # Top 20 most called queries
    echo "=== Top 20 Most Called Queries ===" >> "$OUT_DIR/db-profile.txt"
    run_psql -c "
SELECT
    calls,
    round(total_exec_time::numeric, 2) AS total_ms,
    round(mean_exec_time::numeric, 2) AS mean_ms,
    rows,
    LEFT(query, 120) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY calls DESC
LIMIT 20;
" >> "$OUT_DIR/db-profile.txt" 2>/dev/null || true

else
    log_warn "pg_stat_statements not available — enable in docker-compose"
    echo "(pg_stat_statements not available)" >> "$OUT_DIR/db-profile.txt"
fi

echo "" >> "$OUT_DIR/db-profile.txt"

# --- Sequential scans (missing indexes) ---
echo "=== Tables with High Sequential Scan Count (potential missing indexes) ===" >> "$OUT_DIR/db-profile.txt"
run_psql -c "
SELECT
    schemaname || '.' || relname AS table,
    seq_scan,
    seq_tup_read,
    idx_scan,
    CASE WHEN seq_scan + idx_scan > 0
        THEN round(100.0 * seq_scan / (seq_scan + idx_scan), 1)
        ELSE 0
    END AS seq_pct,
    n_live_tup AS rows
FROM pg_stat_user_tables
WHERE seq_scan > 0
ORDER BY seq_tup_read DESC
LIMIT 20;
" >> "$OUT_DIR/db-profile.txt" 2>/dev/null \
    && log_ok "Sequential scan report saved" \
    || log_warn "Table stats query failed"

echo "" >> "$OUT_DIR/db-profile.txt"

# --- Unused indexes ---
echo "=== Unused Indexes (0 scans, waste of space/write overhead) ===" >> "$OUT_DIR/db-profile.txt"
run_psql -c "
SELECT
    schemaname || '.' || relname AS table,
    indexrelname AS index,
    idx_scan AS scans,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
    AND indexrelname NOT LIKE '%_pkey'
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 20;
" >> "$OUT_DIR/db-profile.txt" 2>/dev/null \
    && log_ok "Unused indexes report saved" \
    || log_warn "Index stats query failed"

echo "" >> "$OUT_DIR/db-profile.txt"

# --- Table sizes ---
echo "=== Table Sizes ===" >> "$OUT_DIR/db-profile.txt"
run_psql -c "
SELECT
    schemaname || '.' || relname AS table,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size,
    n_live_tup AS rows
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
" >> "$OUT_DIR/db-profile.txt" 2>/dev/null \
    && log_ok "Table sizes report saved" \
    || log_warn "Table size query failed"

echo "" >> "$OUT_DIR/db-profile.txt"

# --- Cache hit ratio ---
echo "=== Cache Hit Ratio ===" >> "$OUT_DIR/db-profile.txt"
run_psql -c "
SELECT
    'index' AS type,
    sum(idx_blks_hit) AS hits,
    sum(idx_blks_read) AS reads,
    CASE WHEN sum(idx_blks_hit) + sum(idx_blks_read) > 0
        THEN round(100.0 * sum(idx_blks_hit) / (sum(idx_blks_hit) + sum(idx_blks_read)), 2)
        ELSE 100
    END AS hit_pct
FROM pg_statio_user_indexes
UNION ALL
SELECT
    'table' AS type,
    sum(heap_blks_hit) AS hits,
    sum(heap_blks_read) AS reads,
    CASE WHEN sum(heap_blks_hit) + sum(heap_blks_read) > 0
        THEN round(100.0 * sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read)), 2)
        ELSE 100
    END AS hit_pct
FROM pg_statio_user_tables;
" >> "$OUT_DIR/db-profile.txt" 2>/dev/null \
    && log_ok "Cache hit ratio saved" \
    || log_warn "Cache stats query failed"

# --- Generate CSV summaries for programmatic consumption ---
run_psql -t -A -F',' -c "
SELECT
    schemaname || '.' || relname AS table_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    CASE WHEN seq_scan + idx_scan > 0
        THEN round(100.0 * seq_scan / (seq_scan + idx_scan), 1)
        ELSE 0
    END AS seq_pct,
    n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY seq_tup_read DESC;
" > "$OUT_DIR/table-stats.csv" 2>/dev/null \
    && (echo "table,seq_scan,seq_tup_read,idx_scan,seq_pct,rows" | cat - "$OUT_DIR/table-stats.csv" > /tmp/db-csv-tmp && mv /tmp/db-csv-tmp "$OUT_DIR/table-stats.csv") \
    && log_ok "Table stats CSV → $OUT_DIR/table-stats.csv" \
    || true

log_ok "Database profile → $OUT_DIR/db-profile.txt"
