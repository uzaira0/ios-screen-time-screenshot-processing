#!/usr/bin/env bun
/**
 * Generate N unique screenshot PNGs for the stress test by cloning the four
 * real fixtures and injecting a unique `tEXt` chunk into each clone.
 *
 * Why a tEXt chunk: every browser PNG decoder ignores unknown ancillary
 * chunks, so the image renders identically. The byte change makes each
 * file's SHA-256 content hash unique, which exercises the WASM upload
 * dedup path correctly (1000 distinct screenshots, not 1 deduped).
 *
 * Usage:
 *   bun run scripts/generate-stress-fixtures.ts [count] [out-dir]
 *
 * Defaults: count=1000, out-dir=/tmp/test-screenshots-1000
 */

import { readFileSync, mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { join } from "node:path";

const COUNT = Number(process.argv[2] ?? 1000);
const OUT_DIR = process.argv[3] ?? "/tmp/test-screenshots-1000";
const FIXTURE_DIR = new URL("../../tests/fixtures/images/", import.meta.url).pathname;
const FIXTURES = [
  "IMG_0806 Cropped.png",
  "IMG_0807 Cropped.png",
  "IMG_0808 Cropped.png",
  "IMG_0809 Cropped.png",
];

// CRC-32 per the PNG spec (polynomial 0xEDB88320, inverted output).
const CRC_TABLE: number[] = (() => {
  const t: number[] = [];
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    }
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf: Buffer): number {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) {
    c = CRC_TABLE[(c ^ buf[i]!) & 0xFF]! ^ (c >>> 8);
  }
  return (c ^ 0xFFFFFFFF) >>> 0;
}

function makeTextChunk(keyword: string, text: string): Buffer {
  // tEXt: keyword (1-79 bytes Latin-1) + null + text (Latin-1, no null).
  const data = Buffer.concat([
    Buffer.from(keyword, "latin1"),
    Buffer.from([0]),
    Buffer.from(text, "latin1"),
  ]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const type = Buffer.from("tEXt", "latin1");
  const crcInput = Buffer.concat([type, data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(crcInput), 0);
  return Buffer.concat([length, type, data, crc]);
}

function injectTextChunkBeforeIEND(png: Buffer, chunk: Buffer): Buffer {
  // PNG = 8-byte signature, then chunks: [length(4) | type(4) | data(length) | crc(4)].
  // Insert our chunk before the terminating IEND chunk.
  const sig = png.subarray(0, 8);
  let offset = 8;
  let iendStart = -1;
  while (offset < png.length) {
    const len = png.readUInt32BE(offset);
    const type = png.subarray(offset + 4, offset + 8).toString("latin1");
    const next = offset + 12 + len;
    if (type === "IEND") {
      iendStart = offset;
      break;
    }
    offset = next;
  }
  if (iendStart < 0) {
    throw new Error("PNG: no IEND chunk found");
  }
  return Buffer.concat([
    sig,
    png.subarray(8, iendStart),
    chunk,
    png.subarray(iendStart),
  ]);
}

function main() {
  if (existsSync(OUT_DIR)) rmSync(OUT_DIR, { recursive: true, force: true });
  mkdirSync(OUT_DIR, { recursive: true });

  const sources = FIXTURES.map((name) => readFileSync(join(FIXTURE_DIR, name)));
  if (sources.some((s) => s.length === 0)) {
    throw new Error(`Empty fixture in ${FIXTURE_DIR}`);
  }

  const padWidth = String(COUNT).length;
  for (let i = 0; i < COUNT; i++) {
    const src = sources[i % sources.length]!;
    // Unique-per-clone tEXt chunk. The keyword "StressIndex" is arbitrary.
    const chunk = makeTextChunk("StressIndex", String(i).padStart(padWidth, "0"));
    const out = injectTextChunkBeforeIEND(src, chunk);
    const idx = String(i).padStart(padWidth, "0");
    writeFileSync(join(OUT_DIR, `screenshot_${idx}.png`), out);
  }

  console.log(`Wrote ${COUNT} fixtures to ${OUT_DIR}`);
}

main();
