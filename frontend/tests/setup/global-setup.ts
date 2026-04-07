import { FullConfig } from "@playwright/test";
import { exec, spawn } from "child_process";
import { promisify } from "util";
import * as path from "path";
import * as fs from "fs";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const execAsync = promisify(exec);

const TEST_DATABASE_URL =
  "postgresql+asyncpg://screenshot:screenshot@localhost:5435/screenshot_annotations_test";

// Paths for test fixtures
const PROJECT_ROOT = path.resolve(__dirname, "../../..");
const FIXTURES_DIR = path.join(PROJECT_ROOT, "tests/fixtures/images");
const UPLOADS_DIR = path.join(PROJECT_ROOT, "uploads/screenshots/TEST-GROUP");

/**
 * Run alembic migrations on the test database
 */
async function runMigrations(): Promise<void> {
  const projectRoot = path.resolve(__dirname, "../../..");

  return new Promise((resolve, reject) => {
    const isWindows = process.platform === "win32";
    const shell = isWindows ? true : "/bin/sh";

    const alembic = spawn("alembic", ["upgrade", "head"], {
      cwd: projectRoot,
      env: {
        ...process.env,
        DATABASE_URL: TEST_DATABASE_URL,
      },
      shell,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    alembic.stdout?.on("data", (data) => {
      stdout += data.toString();
    });

    alembic.stderr?.on("data", (data) => {
      stderr += data.toString();
    });

    alembic.on("close", (code) => {
      if (code === 0) {
        console.log(stdout || "Migrations complete");
        resolve();
      } else {
        console.error("Migration stderr:", stderr);
        reject(new Error(`Alembic failed with code ${code}`));
      }
    });

    alembic.on("error", (err) => {
      reject(err);
    });

    // Timeout after 60s
    setTimeout(() => {
      alembic.kill();
      reject(new Error("Migration timeout"));
    }, 60000);
  });
}

/**
 * Truncate all test tables using docker exec
 */
async function truncateTables(): Promise<void> {
  // Simple truncate of known tables (CASCADE handles dependencies)
  const truncateSQL =
    "TRUNCATE screenshots, annotations, users, groups, consensus_results, user_queue_states, processing_issues, annotation_audit_logs CASCADE;";

  try {
    const { stdout, stderr } = await execAsync(
      `docker exec screenshot-postgres-dev psql -U screenshot -d screenshot_annotations_test -c "${truncateSQL}"`,
      { timeout: 30000 }
    );
    console.log(stdout || "Tables truncated");
    if (stderr) console.warn("Truncate warning:", stderr);
  } catch (error: unknown) {
    // Tables might not exist yet - that's fine
    const errMsg = error instanceof Error ? error.message : String(error);
    if (
      errMsg.includes("does not exist") ||
      errMsg.includes("relation") ||
      errMsg.includes("table")
    ) {
      console.log("Some tables don't exist yet - continuing");
    } else {
      console.warn("Truncate error (non-fatal):", errMsg);
    }
  }
}

/**
 * Create groups table if not exists (not in migrations yet)
 */
async function ensureGroupsTable(): Promise<void> {
  const createGroupsSQL = `
    CREATE TABLE IF NOT EXISTS groups (
      id VARCHAR(100) PRIMARY KEY,
      name VARCHAR(255) NOT NULL,
      image_type VARCHAR(50) NOT NULL DEFAULT 'screen_time',
      created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_groups_id ON groups(id);
  `;

  try {
    await execAsync(
      `docker exec screenshot-postgres-dev psql -U screenshot -d screenshot_annotations_test -c "${createGroupsSQL.replace(/\n/g, " ")}"`,
      { timeout: 30000 }
    );
    console.log("Groups table ensured");
  } catch (error) {
    console.warn("Could not create groups table:", error);
  }
}

/**
 * Copy test fixture images to uploads directory
 */
async function copyTestImages(): Promise<string[]> {
  // Create uploads directory if it doesn't exist
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });

  // Get fixture images
  const fixtureImages = fs.readdirSync(FIXTURES_DIR).filter((f) => f.endsWith(".png"));

  const copiedPaths: string[] = [];
  for (let i = 0; i < Math.min(5, fixtureImages.length); i++) {
    const srcPath = path.join(FIXTURES_DIR, fixtureImages[i]);
    const destFilename = `test_screenshot_${i + 1}.png`;
    const destPath = path.join(UPLOADS_DIR, destFilename);

    fs.copyFileSync(srcPath, destPath);
    // Store relative path from project root for database
    copiedPaths.push(`uploads/screenshots/TEST-GROUP/${destFilename}`);
  }

  console.log(`Copied ${copiedPaths.length} test images`);
  return copiedPaths;
}

/**
 * Seed test data for E2E tests
 */
async function seedTestData(): Promise<void> {
  // Copy test images first and get their paths
  const imagePaths = await copyTestImages();

  // Use separate commands to avoid shell escaping issues with JSON
  const commands = [
    // Create test group
    `INSERT INTO groups (id, name, image_type) VALUES ('TEST-GROUP', 'Test Group', 'screen_time') ON CONFLICT (id) DO NOTHING`,
    // Create test screenshots - SQLAlchemy StrEnum stores enum NAMES in uppercase (COMPLETED, PENDING)
    // Use actual paths from copied test images
    ...imagePaths.map(
      (filePath, idx) =>
        `INSERT INTO screenshots (id, group_id, file_path, image_type, status, target_annotations, current_annotation_count, has_blocking_issues, processing_status, annotation_status, extracted_title, extracted_total, uploaded_at) VALUES (${idx + 1}, 'TEST-GROUP', '${filePath}', 'screen_time', 'pending', 2, 0, false, 'COMPLETED', 'PENDING', 'Test App ${idx + 1}', '${30 + idx * 15}m', NOW()) ON CONFLICT (id) DO NOTHING`
    ),
    // Reset sequence
    `SELECT setval('screenshots_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM screenshots), false)`,
  ];

  try {
    for (const cmd of commands) {
      await execAsync(
        `docker exec screenshot-postgres-dev psql -U screenshot -d screenshot_annotations_test -c "${cmd}"`,
        { timeout: 30000 }
      );
    }
    console.log("Test data seeded");
  } catch (error: unknown) {
    const errMsg = error instanceof Error ? error.message : String(error);
    console.warn("Seed error (non-fatal):", errMsg);
  }
}

/**
 * Global setup that runs before all tests.
 * Resets the test database to a clean state.
 */
async function globalSetup(_config: FullConfig): Promise<void> {
  console.log("\n=== Global Setup: Resetting Test Database ===\n");

  try {
    // Run alembic migrations on the test database
    console.log("Running database migrations...");
    await runMigrations();

    // Create groups table if not exists (not in migrations)
    console.log("Ensuring groups table exists...");
    await ensureGroupsTable();

    // Truncate all tables for a clean slate
    console.log("Truncating test tables...");
    await truncateTables();

    // Seed test data
    console.log("Seeding test data...");
    await seedTestData();

    console.log("\n=== Test Database Ready ===\n");
  } catch (error) {
    console.error("Global setup error:", error);
    // Don't fail - let tests attempt to run anyway
    console.log("Continuing with tests despite setup error...");
  }
}

export default globalSetup;
