/**
 * Tesseract.js benchmark — outputs JSON lines for each image.
 */
import Tesseract from 'tesseract.js';
import fs from 'fs';
import path from 'path';

const IMG_DIR = process.argv[2] || '/images';
const RUNS = 3;

const files = fs.readdirSync(IMG_DIR)
  .filter(f => /\.(png|jpg|jpeg)$/i.test(f))
  .sort();

const worker = await Tesseract.createWorker('eng');

for (const fname of files) {
  const imgPath = path.join(IMG_DIR, fname);

  for (const psm of [3, 6]) {
    await worker.setParameters({ tessedit_pageseg_mode: String(psm) });

    const latencies = [];
    let lastText = '';
    let lastBboxes = [];

    for (let run = 0; run < RUNS; run++) {
      const t0 = performance.now();
      const { data } = await worker.recognize(imgPath);
      const elapsed = performance.now() - t0;
      latencies.push(elapsed);

      lastText = data.text.trim();
      lastBboxes = data.words.map(w => ({
        text: w.text,
        x: w.bbox.x0,
        y: w.bbox.y0,
        w: w.bbox.x1 - w.bbox.x0,
        h: w.bbox.y1 - w.bbox.y0,
        conf: w.confidence,
      }));
    }

    latencies.sort((a, b) => a - b);
    const median = latencies[Math.floor(latencies.length / 2)];

    console.log(JSON.stringify({
      binding: 'tesseract_js',
      image: fname,
      psm,
      text: lastText,
      bboxes: lastBboxes,
      bbox_count: lastBboxes.length,
      latency_ms: Math.round(median * 10) / 10,
    }));
  }
}

await worker.terminate();
