#!/usr/bin/env python3
"""pytesseract benchmark — outputs JSON lines for each image."""
import json, os, sys, time
import cv2
import numpy as np
from pytesseract import pytesseract, Output

IMG_DIR = sys.argv[1] if len(sys.argv) > 1 else "/images"
RUNS = 3

for fname in sorted(os.listdir(IMG_DIR)):
    if not fname.lower().endswith((".png", ".jpg", ".jpeg")):
        continue
    path = os.path.join(IMG_DIR, fname)
    img = cv2.imread(path)
    if img is None:
        continue

    for psm in [3, 6]:
        config = f"--psm {psm}"
        latencies = []
        text = ""
        bboxes = []

        for _ in range(RUNS):
            t0 = time.perf_counter()
            text = pytesseract.image_to_string(img, config=config).strip()
            data = pytesseract.image_to_data(img, config=config, output_type=Output.DICT)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)

            bboxes = []
            for i in range(len(data["text"])):
                if data["text"][i].strip():
                    bboxes.append({
                        "text": data["text"][i],
                        "x": data["left"][i], "y": data["top"][i],
                        "w": data["width"][i], "h": data["height"][i],
                        "conf": data["conf"][i],
                    })

        latencies.sort()
        median_ms = latencies[len(latencies) // 2]

        print(json.dumps({
            "binding": "pytesseract",
            "image": fname,
            "psm": psm,
            "text": text,
            "bboxes": bboxes,
            "bbox_count": len(bboxes),
            "latency_ms": round(median_ms, 1),
        }), flush=True)
