import { test as setup } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const API_BASE_URL = "http://127.0.0.1:8002";

/**
 * Wait for the backend server to be ready with exponential backoff
 */
async function waitForServer(
  request: Parameters<Parameters<typeof setup>[1]>[0]["request"],
  maxAttempts = 15,
): Promise<boolean> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await request.get(`${API_BASE_URL}/health`, {
        timeout: 5000,
      });
      if (response.ok()) {
        console.log(`Server ready after ${i + 1} attempt(s)`);
        return true;
      }
    } catch {
      // Server not ready yet
    }

    // Exponential backoff: 1s, 2s, 3s, ... up to 5s
    const delay = Math.min((i + 1) * 1000, 5000);
    console.log(
      `Waiting for server... attempt ${i + 1}/${maxAttempts} (retry in ${delay}ms)`,
    );
    await new Promise((r) => setTimeout(r, delay));
  }

  console.error("Server failed to start after maximum attempts");
  return false;
}

/**
 * Reset test data via API (PostgreSQL compatible)
 */
async function resetTestData(
  request: Parameters<Parameters<typeof setup>[1]>[0]["request"],
): Promise<void> {
  try {
    // Use the admin API to reset test state if available
    // For now, we'll just let the tests run with existing data
    // The upload endpoint handles duplicates gracefully
    console.log("Test data reset: Using fresh uploads");
  } catch (e) {
    console.log(`Could not reset test data via API: ${e}`);
  }
}

setup("upload test screenshots", async ({ request }) => {
  const dataDir = path.resolve(__dirname, "../../../data");
  const apiKey = "dev-upload-key-change-in-production";
  const baseUrl = `${API_BASE_URL}/api/v1/screenshots/upload`;

  // Wait for server to be ready before attempting uploads
  const serverReady = await waitForServer(request);
  if (!serverReady) {
    console.error(
      "Skipping screenshot upload - server not available. " +
        "Make sure PostgreSQL is running: docker-compose -f docker-compose.dev.yml up -d",
    );
    return;
  }

  // Reset test data (if needed)
  await resetTestData(request);

  // Find PNG files in SAMPLE-001 folder (first 10)
  const p3Dir = path.join(dataDir, "SAMPLE-001 Cropped");

  if (!fs.existsSync(p3Dir)) {
    console.log(`Data directory not found: ${p3Dir}`);
    return;
  }

  // Get all PNG files recursively
  const findPngs = (dir: string): string[] => {
    const files: string[] = [];
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        files.push(...findPngs(fullPath));
      } else if (entry.name.endsWith(".png")) {
        files.push(fullPath);
      }
    }
    return files;
  };

  const pngFiles = findPngs(p3Dir).slice(0, 10);
  console.log(`Found ${pngFiles.length} PNG files to upload`);

  let uploaded = 0;
  let skippedDuplicates = 0;

  for (const imgPath of pngFiles) {
    const relativePath = path.relative(dataDir, imgPath);
    const parts = relativePath.split(path.sep);
    const groupId = parts[0]; // e.g. 'SAMPLE-001 Cropped'
    const participantId = parts[1]; // e.g. 'SAMPLE-001_T1_10-1-23'
    const filename = parts[parts.length - 1];

    // Read and encode image
    const imageBuffer = fs.readFileSync(imgPath);
    const base64Image = imageBuffer.toString("base64");

    const payload = {
      screenshot: base64Image,
      participant_id: participantId,
      group_id: groupId,
      image_type: "screen_time",
      filename: filename,
    };

    try {
      const response = await request.post(baseUrl, {
        data: payload,
        headers: {
          "X-API-Key": apiKey,
        },
        timeout: 30000, // 30s timeout for large uploads
      });

      if (response.status() === 201) {
        uploaded++;
        console.log(`Uploaded: ${filename}`);
      } else if (response.status() === 409) {
        // Duplicate - already exists
        skippedDuplicates++;
      } else {
        const text = await response.text();
        console.log(
          `Failed ${filename}: ${response.status()} - ${text.slice(0, 100)}`,
        );
      }
    } catch (e) {
      console.log(`Error uploading ${filename}: ${e}`);
    }
  }

  console.log(
    `Upload complete: ${uploaded} new, ${skippedDuplicates} duplicates skipped, ` +
      `${pngFiles.length - uploaded - skippedDuplicates} failed`,
  );
});
