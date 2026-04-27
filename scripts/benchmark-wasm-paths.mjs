#!/usr/bin/env node
/**
 * WASM Path A vs Path B benchmark.
 *
 * Path A: wasm-pack (wasm32-unknown-unknown) — Rust grid-detect + bar-extract, no OCR.
 * Path B: Emscripten (wasm32-unknown-emscripten) — full leptess (OCR + grid + bars).
 *
 * Also benchmarks the image-decoding step with both `canvas` and `jimp`.
 *
 * Usage:
 *   node scripts/benchmark-wasm-paths.mjs [--iterations N] [--image path/to/image.png]
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join, resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { performance } from "perf_hooks";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

const args = process.argv.slice(2);
const iterIdx = args.indexOf("--iterations");
const ITERATIONS = iterIdx >= 0 ? parseInt(args[iterIdx + 1], 10) : 10;
const imageIdx = args.indexOf("--image");
const SINGLE_IMAGE = imageIdx >= 0 ? resolve(args[imageIdx + 1]) : null;

const FIXTURE_DIR = join(ROOT, "tests/fixtures/images");
const PATH_A_DIR = join(ROOT, "scripts/.bench-wasm-a");
const PATH_B_JS = join(ROOT, "frontend/public/pipeline-em/IosScreenTimePipeline.js");
const PATH_B_WASM = join(ROOT, "frontend/public/pipeline-em/IosScreenTimePipeline.wasm");
const PATH_B_TESSDATA = join(ROOT, "frontend/public/pipeline-em/eng.traineddata");

function getFixtureImages() {
  if (SINGLE_IMAGE) return [SINGLE_IMAGE];
  if (!existsSync(FIXTURE_DIR)) { console.error(`Missing: ${FIXTURE_DIR}`); process.exit(1); }
  return readdirSync(FIXTURE_DIR)
    .filter((f) => /\.(png|jpg|jpeg)$/i.test(f))
    .slice(0, 5)
    .map((f) => join(FIXTURE_DIR, f));
}

function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

// ── Image decoders ────────────────────────────────────────────────────────────

async function imageToRgbaCanvas(imagePath) {
  const { createCanvas, loadImage } = require("canvas");
  const img = await loadImage(imagePath);
  const canvas = createCanvas(img.width, img.height);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0);
  const data = ctx.getImageData(0, 0, img.width, img.height);
  return { rgba: new Uint8Array(data.data.buffer), width: img.width, height: img.height };
}

async function imageToRgbaJimp(imagePath) {
  const { Jimp } = require("jimp");
  const img = await Jimp.read(imagePath);
  return {
    rgba: new Uint8Array(img.bitmap.data.buffer),
    width: img.bitmap.width,
    height: img.bitmap.height,
  };
}

// ── Benchmark: image decode ───────────────────────────────────────────────────

async function benchDecode(images) {
  const rows = [];
  for (const imgPath of images) {
    const name = imgPath.split("/").pop();

    const canvasTimes = [];
    for (let i = 0; i < ITERATIONS; i++) {
      const t0 = performance.now();
      await imageToRgbaCanvas(imgPath);
      canvasTimes.push(performance.now() - t0);
    }

    const jimpTimes = [];
    for (let i = 0; i < ITERATIONS; i++) {
      const t0 = performance.now();
      await imageToRgbaJimp(imgPath);
      jimpTimes.push(performance.now() - t0);
    }

    rows.push({
      name,
      canvas_ms: median(canvasTimes).toFixed(2),
      jimp_ms: median(jimpTimes).toFixed(2),
    });
  }
  return rows;
}

// ── Benchmark: Path A (wasm-bindgen, grid-detect only) ───────────────────────

async function benchPathA(images) {
  const pkgJs = join(PATH_A_DIR, "ios_screen_time_image_pipeline.js");
  if (!existsSync(pkgJs)) {
    return { available: false, reason: `Path A not built at ${PATH_A_DIR}` };
  }
  const mod = require(pkgJs); // synchronous CJS — wasm already loaded

  const times = [];
  const results = [];

  for (const imgPath of images) {
    const { rgba, width, height } = await imageToRgbaCanvas(imgPath);
    const runs = [];
    let last;
    for (let i = 0; i < ITERATIONS; i++) {
      const t0 = performance.now();
      last = mod.detect_grid(rgba, width, height);
      runs.push(performance.now() - t0);
    }
    const med = median(runs);
    times.push(med);
    results.push({ name: imgPath.split("/").pop(), median_ms: med.toFixed(2), min_ms: Math.min(...runs).toFixed(2), result: last });
  }

  return {
    available: true,
    label: "Path A  (wasm-bindgen · grid-detect · no OCR)",
    avg_ms: (times.reduce((a, b) => a + b, 0) / times.length).toFixed(2),
    per_image: results,
  };
}

// ── Benchmark: Path B (Emscripten + leptess) ─────────────────────────────────

async function benchPathB(images) {
  if (!existsSync(PATH_B_JS)) {
    return {
      available: false,
      reason: `Path B not built. Run:\n  docker build -t ios-screen-time-wasm-builder docker/wasm-build/\n  docker run --rm -v $(pwd):/app ios-screen-time-wasm-builder scripts/build-wasm-emscripten.sh`,
    };
  }

  const jsSource = readFileSync(PATH_B_JS, "utf8");
  const wasmBinary = readFileSync(PATH_B_WASM);
  const tessdata = readFileSync(PATH_B_TESSDATA);

  // eslint-disable-next-line no-new-func
  const getFactory = new Function(`${jsSource}; return IosScreenTimePipeline;`);
  const factory = getFactory();
  if (typeof factory !== "function") {
    return { available: false, reason: "Factory not found in Emscripten JS output" };
  }

  const mod = await factory({ wasmBinary: wasmBinary.buffer, locateFile: () => PATH_B_WASM });
  mod.FS.mkdir("/tesseract");
  mod.FS.writeFile("/tesseract/eng.traineddata", tessdata);

  const OUT = 65536;
  const times = [];
  const results = [];

  // Run detect_grid (no OCR, apples-to-apples with Path A) then full pipeline.
  const runGridOnly = [];
  const runFull = [];

  for (const imgPath of images) {
    const { rgba, width, height } = await imageToRgbaCanvas(imgPath);
    const gridRuns = [];
    const fullRuns = [];
    let lastGrid, lastFull;

    for (let i = 0; i < ITERATIONS; i++) {
      const rPtr = mod._pipeline_alloc(rgba.length);
      const oPtr = mod._pipeline_alloc(OUT);
      mod.HEAPU8.set(rgba, rPtr);

      // Grid-only (comparable to Path A — method=1 forces LineBased, no OCR)
      const t0 = performance.now();
      const wGrid = mod._pipeline_detect_grid(rPtr, rgba.length, width, height, 1, oPtr, OUT);
      gridRuns.push(performance.now() - t0);
      if (wGrid > 0) lastGrid = JSON.parse(new TextDecoder().decode(mod.HEAPU8.subarray(oPtr, oPtr + wGrid)));

      // Full pipeline (grid + bars + OCR)
      const tb = new TextEncoder().encode("screen_time\0");
      const tPtr = mod._pipeline_alloc(tb.length);
      mod.HEAPU8.set(tb, tPtr);
      const t1 = performance.now();
      const wFull = mod._pipeline_process(rPtr, rgba.length, width, height, tPtr, 0, -1, -1, -1, -1, oPtr, OUT);
      fullRuns.push(performance.now() - t1);
      if (wFull > 0) lastFull = JSON.parse(new TextDecoder().decode(mod.HEAPU8.subarray(oPtr, oPtr + wFull)));

      mod._pipeline_free(rPtr, rgba.length);
      mod._pipeline_free(oPtr, OUT);
      mod._pipeline_free(tPtr, tb.length);
    }

    const gMed = median(gridRuns);
    const fMed = median(fullRuns);
    runGridOnly.push({ name: imgPath.split("/").pop(), median_ms: gMed.toFixed(2), min_ms: Math.min(...gridRuns).toFixed(2), result: lastGrid });
    runFull.push({ name: imgPath.split("/").pop(), median_ms: fMed.toFixed(2), min_ms: Math.min(...fullRuns).toFixed(2), result: lastFull });
    times.push(gMed);
  }

  return {
    available: true,
    label: "Path B  (Emscripten · grid-detect only, no OCR)",
    labelFull: "Path B  (Emscripten · full pipeline: grid + bars + OCR)",
    avg_ms: (times.reduce((a, b) => a + b, 0) / times.length).toFixed(2),
    per_image: runGridOnly,
    per_image_full: runFull,
  };
}

// ── Output ────────────────────────────────────────────────────────────────────

function printSection(label, rows, colFn) {
  console.log(`\n  ── ${label}`);
  for (const r of rows) console.log(`    ${r.name.padEnd(42)} ${colFn(r)}`);
}

async function main() {
  const images = getFixtureImages();
  console.log(`\n╔══ WASM Benchmark: Path A vs Path B ═══════════════════════╗`);
  console.log(`  Images: ${images.length}   Iterations per image: ${ITERATIONS}   Node ${process.version}`);
  console.log(`  ${new Date().toISOString()}`);
  console.log(`╚════════════════════════════════════════════════════════════╝`);

  // Run all benchmarks
  console.log("\n[1/3] Image decode benchmark (canvas vs jimp)…");
  const decodeRows = await benchDecode(images);
  printSection("canvas decode", decodeRows, (r) => `${String(r.canvas_ms).padStart(7)} ms`);
  printSection("jimp   decode", decodeRows, (r) => `${String(r.jimp_ms).padStart(7)} ms`);
  const avgCanvas = (decodeRows.reduce((s, r) => s + parseFloat(r.canvas_ms), 0) / decodeRows.length).toFixed(2);
  const avgJimp   = (decodeRows.reduce((s, r) => s + parseFloat(r.jimp_ms), 0) / decodeRows.length).toFixed(2);
  const decodeWinner = parseFloat(avgCanvas) < parseFloat(avgJimp) ? "canvas" : "jimp";
  console.log(`\n  canvas avg ${avgCanvas} ms   jimp avg ${avgJimp} ms   → ${decodeWinner} is faster`);

  console.log("\n[2/3] Path A benchmark (wasm-bindgen grid-detect)…");
  const a = await benchPathA(images);
  if (!a.available) {
    console.log(`  [SKIP] ${a.reason}`);
  } else {
    printSection(a.label, a.per_image, (r) => `median ${String(r.median_ms).padStart(7)} ms   min ${String(r.min_ms).padStart(7)} ms`);
    console.log(`\n  average median: ${a.avg_ms} ms`);
  }

  console.log("\n[3/3] Path B benchmark (Emscripten grid-detect + full pipeline)…");
  const b = await benchPathB(images);
  if (!b.available) {
    console.log(`  [SKIP] ${b.reason}`);
  } else {
    printSection(b.label, b.per_image, (r) => `median ${String(r.median_ms).padStart(7)} ms   min ${String(r.min_ms).padStart(7)} ms`);
    console.log(`\n  grid-detect avg: ${b.avg_ms} ms`);
    if (b.per_image_full) {
      const fullAvg = (b.per_image_full.reduce((s, r) => s + parseFloat(r.median_ms), 0) / b.per_image_full.length).toFixed(2);
      printSection(b.labelFull, b.per_image_full, (r) => `median ${String(r.median_ms).padStart(7)} ms   min ${String(r.min_ms).padStart(7)} ms`);
      console.log(`\n  ── OCR results`);
      for (const r of b.per_image_full) {
        const res = r.result || {};
        const title = res.title ?? "(null)";
        const total = res.total_text ?? "(null)";
        const ocrErr = res.ocr_error ? `  ⚠ ocr_error: ${res.ocr_error}` : "";
        console.log(`    ${r.name.padEnd(42)} title=${JSON.stringify(title)}  total_text=${JSON.stringify(total)}${ocrErr}`);
      }
      console.log(`\n  full pipeline avg: ${fullAvg} ms`);
    }
  }

  if (a.available && b.available) {
    const aMs = parseFloat(a.avg_ms);
    const bMs = parseFloat(b.avg_ms);
    const ratio = (Math.max(aMs, bMs) / Math.min(aMs, bMs)).toFixed(2);
    const faster = aMs < bMs ? "A (wasm-bindgen)" : "B (Emscripten)";
    console.log(`\n  ══ Summary (grid-detect apples-to-apples) ══`);
    console.log(`  Path A avg: ${a.avg_ms} ms   Path B grid-detect avg: ${b.avg_ms} ms`);
    console.log(`  Path ${faster} is ${ratio}x faster.`);
    console.log(`  Path B full pipeline (grid + bars + OCR) adds OCR overhead on top of grid-detect.`);
  }

  console.log();
}

main().catch((e) => { console.error(e); process.exit(1); });
