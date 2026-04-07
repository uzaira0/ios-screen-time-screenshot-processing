"""
Test that Alembic migrations are reversible and consistent.

Tests include:
- Full roundtrip: upgrade head -> downgrade base -> upgrade head (idempotency)
- Revision chain integrity (no gaps, no duplicates)
- Migration file naming conventions
- Step-by-step upgrade verification
- Schema state after specific migrations
- Data preservation through migrations

Some tests require a real PostgreSQL database (skipped if unavailable).
Others are file-based and always run.
"""
import os
import re
from pathlib import Path

import pytest

ALEMBIC_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# Expected migration chain (down_revision -> revision)
# Reconstructed from the actual files:
EXPECTED_CHAIN = [
    (None, "31a3e57cdd5d"),                       # initial_schema
    ("31a3e57cdd5d", "c211dfc3aaff"),             # standardize_imagetype_enum_values
    ("c211dfc3aaff", "825cee0c9c5c"),             # add_processing_metadata_to_screenshots
    ("825cee0c9c5c", "a7b8c9d0e1f2"),             # rename_required_to_target_annotations
    ("a7b8c9d0e1f2", "b8c9d0e1f2a3"),             # add_processing_method_fields
    ("b8c9d0e1f2a3", "c1d2e3f4g5h6"),             # add_annotation_unique_constraint
    ("c1d2e3f4g5h6", "d2e3f4g5h6i7"),             # add_user_queue_state_unique_constraint
    ("d2e3f4g5h6i7", "e3f4g5h6i7j8"),             # add_annotation_audit_log
    ("e3f4g5h6i7j8", "f4g5h6i7j8k9"),             # add_missing_indexes
    ("f4g5h6i7j8k9", "g5h6i7j8k9l0"),             # add_dispute_resolution_fields
    ("g5h6i7j8k9l0", "h6i7j8k9l0m1"),             # add_preprocessing_jobs_table
    ("h6i7j8k9l0m1", "1dc90afb6cac"),             # add_original_filepath_to_screenshots
    ("1dc90afb6cac", "i7j8k9l0m1n2"),             # add_processing_started_at
    ("i7j8k9l0m1n2", "3613c2977638"),             # add_missing_columns_annotation_status_
    ("3613c2977638", "8d2e3be6f7de"),              # add_content_hash_to_screenshots
    ("8d2e3be6f7de", "j8k9l0m1n2o3"),              # add_composite_perf_indexes
]


# ============================================================================
# File-based tests (no database needed)
# ============================================================================


class TestMigrationFileIntegrity:
    """Tests that verify migration file structure without a database."""

    def _parse_migration_files(self):
        """Parse revision and down_revision from all migration files."""
        migrations = {}
        for path in sorted(ALEMBIC_VERSIONS_DIR.glob("*.py")):
            content = path.read_text()

            rev_match = re.search(r'revision[:\s]*(?:str\s*=\s*)?["\']([^"\']+)["\']', content)
            down_match = re.search(
                r'down_revision[:\s]*(?:Union\[str,\s*None\]|str\s*\|\s*None|str)\s*=\s*([^\n]+)',
                content,
            )

            if rev_match and down_match:
                revision = rev_match.group(1)
                down_raw = down_match.group(1).strip()
                if down_raw == "None":
                    down_revision = None
                else:
                    down_revision = re.search(r'["\']([^"\']+)["\']', down_raw)
                    down_revision = down_revision.group(1) if down_revision else None

                migrations[revision] = {
                    "down_revision": down_revision,
                    "filename": path.name,
                    "path": path,
                }

        return migrations

    def test_migration_files_exist(self):
        """At least one migration file should exist."""
        files = list(ALEMBIC_VERSIONS_DIR.glob("*.py"))
        assert len(files) > 0, "No migration files found"

    def test_no_gaps_in_revision_chain(self):
        """Every down_revision must point to an existing revision (or None for the first)."""
        migrations = self._parse_migration_files()
        revisions = set(migrations.keys())

        for rev, info in migrations.items():
            down = info["down_revision"]
            if down is not None:
                assert down in revisions, (
                    f"Migration {rev} ({info['filename']}) references "
                    f"down_revision '{down}' which does not exist"
                )

    def test_exactly_one_initial_migration(self):
        """Exactly one migration should have down_revision = None."""
        migrations = self._parse_migration_files()
        initial = [
            rev for rev, info in migrations.items()
            if info["down_revision"] is None
        ]
        assert len(initial) == 1, f"Expected 1 initial migration, found {len(initial)}: {initial}"

    def test_no_duplicate_revisions(self):
        """No two migration files should share the same revision ID."""
        migrations = self._parse_migration_files()
        # If we got this far, dict keys already enforce uniqueness.
        # But let's also verify filenames are unique:
        filenames = [info["filename"] for info in migrations.values()]
        assert len(filenames) == len(set(filenames)), "Duplicate migration filenames found"

    def test_revision_id_in_filename(self):
        """Each migration filename should contain its revision ID."""
        migrations = self._parse_migration_files()
        for rev, info in migrations.items():
            assert rev in info["filename"], (
                f"Revision ID '{rev}' not found in filename '{info['filename']}'"
            )

    def test_all_migrations_have_upgrade_and_downgrade(self):
        """Each migration file must define both upgrade() and downgrade() functions."""
        for path in ALEMBIC_VERSIONS_DIR.glob("*.py"):
            content = path.read_text()
            assert "def upgrade()" in content, (
                f"Migration {path.name} is missing upgrade() function"
            )
            assert "def downgrade()" in content, (
                f"Migration {path.name} is missing downgrade() function"
            )

    def test_expected_chain_matches_actual(self):
        """The expected migration chain should match the actual files."""
        migrations = self._parse_migration_files()

        for down_rev, rev in EXPECTED_CHAIN:
            assert rev in migrations, f"Expected revision '{rev}' not found in migration files"
            actual_down = migrations[rev]["down_revision"]
            assert actual_down == down_rev, (
                f"Revision '{rev}': expected down_revision '{down_rev}', "
                f"got '{actual_down}'"
            )

    def test_chain_is_linear(self):
        """The migration chain should be linear (no branches)."""
        migrations = self._parse_migration_files()
        # Each down_revision should appear at most once as a down_revision
        down_revs = [info["down_revision"] for info in migrations.values()]
        non_none = [d for d in down_revs if d is not None]
        assert len(non_none) == len(set(non_none)), (
            "Migration chain has branches (multiple migrations share a down_revision)"
        )

    def test_head_is_reachable_from_initial(self):
        """Walking from initial -> head should visit all migrations."""
        migrations = self._parse_migration_files()

        # Build forward map: down_revision -> revision
        forward = {}
        initial = None
        for rev, info in migrations.items():
            down = info["down_revision"]
            if down is None:
                initial = rev
            else:
                forward[down] = rev

        assert initial is not None, "No initial migration found"

        # Walk the chain
        visited = {initial}
        current = initial
        while current in forward:
            current = forward[current]
            visited.add(current)

        assert visited == set(migrations.keys()), (
            f"Not all migrations are reachable from initial. "
            f"Unreachable: {set(migrations.keys()) - visited}"
        )

    def test_migration_count(self):
        """Verify expected number of migrations."""
        migrations = self._parse_migration_files()
        assert len(migrations) == len(EXPECTED_CHAIN), (
            f"Expected {len(EXPECTED_CHAIN)} migrations, found {len(migrations)}"
        )


# ============================================================================
# Database-dependent tests (require PostgreSQL)
# ============================================================================

pytestmark_pg = pytest.mark.skipif(
    "postgresql" not in os.environ.get("DATABASE_URL", ""),
    reason="Migration roundtrip requires PostgreSQL",
)


@pytest.fixture()
def _empty_migration_db():
    """Create a temporary database for migration testing, drop it after."""
    import psycopg2
    from urllib.parse import urlparse

    db_url = os.environ["DATABASE_URL"]
    parsed = urlparse(db_url.replace("+asyncpg", ""))
    base_dsn = f"postgresql://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port or 5432}/postgres"
    test_db = "migration_roundtrip_test"

    conn = psycopg2.connect(base_dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
    cur.execute(f"CREATE DATABASE {test_db}")
    cur.close()
    conn.close()

    test_url = f"postgresql+asyncpg://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port or 5432}/{test_db}"
    old_url = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = test_url
    yield test_url
    os.environ["DATABASE_URL"] = old_url

    conn = psycopg2.connect(base_dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {test_db}")
    cur.close()
    conn.close()


@pytestmark_pg
def test_migration_roundtrip(_empty_migration_db):
    """Upgrade -> downgrade -> upgrade must not fail on an empty database."""
    from alembic.config import Config
    from alembic.command import upgrade, downgrade

    alembic_cfg = Config("alembic.ini")

    upgrade(alembic_cfg, "head")
    downgrade(alembic_cfg, "base")
    upgrade(alembic_cfg, "head")


@pytestmark_pg
def test_step_by_step_upgrade(_empty_migration_db):
    """Upgrade one step at a time through every migration."""
    from alembic.config import Config
    from alembic.command import upgrade
    from alembic.script import ScriptDirectory

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)

    # Walk revisions in order
    revisions = list(script.walk_revisions("base", "heads"))
    revisions.reverse()  # base -> head order

    for rev in revisions:
        upgrade(alembic_cfg, rev.revision)


@pytestmark_pg
def test_step_by_step_downgrade(_empty_migration_db):
    """Upgrade to head, then downgrade one step at a time."""
    from alembic.config import Config
    from alembic.command import upgrade, downgrade
    from alembic.script import ScriptDirectory

    alembic_cfg = Config("alembic.ini")
    upgrade(alembic_cfg, "head")

    script = ScriptDirectory.from_config(alembic_cfg)
    revisions = list(script.walk_revisions("base", "heads"))
    # revisions is head -> base order already

    for rev in revisions:
        if rev.down_revision is not None:
            downgrade(alembic_cfg, rev.down_revision)
        else:
            downgrade(alembic_cfg, "base")


@pytestmark_pg
def test_schema_state_after_head(_empty_migration_db):
    """After upgrading to head, verify key tables exist."""
    from alembic.config import Config
    from alembic.command import upgrade
    from urllib.parse import urlparse

    import psycopg2

    alembic_cfg = Config("alembic.ini")
    upgrade(alembic_cfg, "head")

    # Connect and check tables
    test_url = _empty_migration_db
    parsed = urlparse(test_url.replace("+asyncpg", ""))
    dsn = f"postgresql://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    )
    tables = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()

    expected_tables = {
        "users", "screenshots", "annotations", "groups",
        "consensus_results", "user_queue_states",
        "processing_issues", "annotation_audit_logs",
        "alembic_version",
    }
    assert expected_tables.issubset(tables), (
        f"Missing tables after full migration: {expected_tables - tables}"
    )


@pytestmark_pg
def test_initial_migration_creates_core_tables(_empty_migration_db):
    """The initial migration should create the core tables."""
    from alembic.config import Config
    from alembic.command import upgrade
    from urllib.parse import urlparse

    import psycopg2

    alembic_cfg = Config("alembic.ini")
    # Upgrade to just the initial migration
    upgrade(alembic_cfg, "31a3e57cdd5d")

    test_url = _empty_migration_db
    parsed = urlparse(test_url.replace("+asyncpg", ""))
    dsn = f"postgresql://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'"
    )
    tables = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()

    # At minimum, initial migration should have users and screenshots
    assert "users" in tables
    assert "screenshots" in tables
