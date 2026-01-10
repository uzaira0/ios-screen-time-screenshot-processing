import { test, expect } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";

/**
 * Upload Dedup Tests (Server Mode)
 *
 * Tests content-hash deduplication on upload endpoints:
 * - First upload of an image succeeds normally
 * - Second upload of the same image returns duplicate indicator
 * - Upload of a different image succeeds normally
 */

const BASE_URL =
  process.env.VITE_API_BASE_URL || "http://localhost:8002/api/v1";
const API_KEY = "dev-upload-key-change-in-production";
const TEST_GROUP = `dedup-test-${Date.now()}`;

/** Create a minimal valid PNG with unique pixel data */
function createTestPng(seed: number): Buffer {
  // Minimal 1x1 PNG with variable pixel color
  const r = seed & 0xff;
  const g = (seed >> 8) & 0xff;
  const b = (seed >> 16) & 0xff;

  // PNG signature
  const signature = Buffer.from([
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
  ]);

  // IHDR chunk: 1x1 pixel, 8-bit RGB
  const ihdrData = Buffer.alloc(13);
  ihdrData.writeUInt32BE(1, 0); // width
  ihdrData.writeUInt32BE(1, 4); // height
  ihdrData[8] = 8; // bit depth
  ihdrData[9] = 2; // color type (RGB)

  const ihdr = createPngChunk("IHDR", ihdrData);

  // IDAT chunk: raw pixel data (filter byte + RGB)
  const rawData = Buffer.from([0x00, r, g, b]); // filter=none + RGB
  const { deflateSync } = require("zlib");
  const compressed = deflateSync(rawData);
  const idat = createPngChunk("IDAT", compressed);

  // IEND chunk
  const iend = createPngChunk("IEND", Buffer.alloc(0));

  return Buffer.concat([signature, ihdr, idat, iend]);
}

function createPngChunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);

  const typeBuffer = Buffer.from(type, "ascii");
  const crcData = Buffer.concat([typeBuffer, data]);

  // CRC32
  const crc = crc32Compute(crcData);
  const crcBuffer = Buffer.alloc(4);
  crcBuffer.writeUInt32BE(crc >>> 0);

  return Buffer.concat([length, typeBuffer, data, crcBuffer]);
}

function crc32Compute(buf: Buffer): number {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc ^= buf[i];
    for (let j = 0; j < 8; j++) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

test.describe("Upload Dedup", () => {
  let tmpDir: string;

  test.beforeAll(async () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dedup-test-"));
  });

  test.afterAll(async () => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  test("first upload succeeds, duplicate is detected, different image succeeds", async ({
    request,
  }) => {
    // Create two distinct test images
    const imageA = createTestPng(0x112233);
    const imageB = createTestPng(0x445566);
    const base64A = imageA.toString("base64");
    const base64B = imageB.toString("base64");

    // --- Upload A (first time) ---
    const resp1 = await request.post(`${BASE_URL}/screenshots/upload`, {
      headers: { "X-API-Key": API_KEY },
      data: {
        screenshot: base64A,
        participant_id: "dedup-test-participant",
        group_id: TEST_GROUP,
        image_type: "screen_time",
        filename: "dedup-a.png",
      },
    });

    if (!resp1.ok()) {
      const body = await resp1.text();
      console.log("Upload A failed:", resp1.status(), body);
      test.skip(true, "Upload API not configured");
      return;
    }

    const data1 = await resp1.json();
    expect(data1.success).toBe(true);
    expect(data1.screenshot_id).toBeDefined();
    expect(data1.duplicate).toBeFalsy();
    const firstId = data1.screenshot_id;

    // --- Upload A again (duplicate) ---
    const resp2 = await request.post(`${BASE_URL}/screenshots/upload`, {
      headers: { "X-API-Key": API_KEY },
      data: {
        screenshot: base64A,
        participant_id: "dedup-test-participant",
        group_id: TEST_GROUP,
        image_type: "screen_time",
        filename: "dedup-a-dup.png",
      },
    });

    expect(resp2.ok()).toBeTruthy();
    const data2 = await resp2.json();
    expect(data2.success).toBe(true);
    expect(data2.duplicate).toBe(true);
    expect(data2.screenshot_id).toBe(firstId);

    // --- Upload B (different image) ---
    const resp3 = await request.post(`${BASE_URL}/screenshots/upload`, {
      headers: { "X-API-Key": API_KEY },
      data: {
        screenshot: base64B,
        participant_id: "dedup-test-participant",
        group_id: TEST_GROUP,
        image_type: "screen_time",
        filename: "dedup-b.png",
      },
    });

    expect(resp3.ok()).toBeTruthy();
    const data3 = await resp3.json();
    expect(data3.success).toBe(true);
    expect(data3.duplicate).toBeFalsy();
    expect(data3.screenshot_id).not.toBe(firstId);
  });
});
