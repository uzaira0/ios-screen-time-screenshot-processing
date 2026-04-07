#!/usr/bin/env python3
"""Analyze OCR benchmark results from all 4 bindings.

Reads all_results.jsonl and produces:
  - summary.md: per-binding stats + recommendation
  - similarity_matrix.md: pairwise text similarity
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

OUT_DIR = Path("profiling-reports/ocr-benchmark")

def levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + (0 if c1 == c2 else 1)))
        prev = curr
    return prev[-1]

def similarity(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 1.0
    ml = max(len(s1), len(s2))
    return 1.0 - levenshtein(s1, s2) / ml if ml else 1.0

def bbox_iou(b1: dict, b2: dict) -> float:
    x1 = max(b1["x"], b2["x"])
    y1 = max(b1["y"], b2["y"])
    x2 = min(b1["x"] + b1["w"], b2["x"] + b2["w"])
    y2 = min(b1["y"] + b1["h"], b2["y"] + b2["h"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = b1["w"] * b1["h"]
    area2 = b2["w"] * b2["h"]
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0

def avg_bbox_iou(bboxes1: list, bboxes2: list) -> float:
    if not bboxes1 or not bboxes2:
        return 0.0
    total = 0.0
    used = set()
    for b1 in bboxes1:
        best, best_j = 0.0, -1
        for j, b2 in enumerate(bboxes2):
            if j in used:
                continue
            iou = bbox_iou(b1, b2)
            if iou > best:
                best, best_j = iou, j
        if best_j >= 0:
            used.add(best_j)
            total += best
    return total / max(len(bboxes1), len(bboxes2))

# Load results
results = []
with open(OUT_DIR / "all_results.jsonl") as f:
    for line in f:
        line = line.strip()
        if line:
            results.append(json.loads(line))

# Group by binding
by_binding = defaultdict(list)
for r in results:
    by_binding[r["binding"]].append(r)

bindings = sorted(by_binding.keys())
print(f"Loaded {len(results)} results from {len(bindings)} bindings: {bindings}")

# Per-binding stats (PSM 3 only for comparison)
stats = {}
for b in bindings:
    psm3 = [r for r in by_binding[b] if r["psm"] == 3]
    lats = [r["latency_ms"] for r in psm3]
    has_bboxes = any(r["bbox_count"] > 0 for r in psm3)
    stats[b] = {
        "images": len(psm3),
        "median_ms": round(statistics.median(lats), 1) if lats else 0,
        "mean_ms": round(statistics.mean(lats), 1) if lats else 0,
        "p95_ms": round(sorted(lats)[int(len(lats) * 0.95)], 1) if lats else 0,
        "min_ms": round(min(lats), 1) if lats else 0,
        "max_ms": round(max(lats), 1) if lats else 0,
        "has_bboxes": has_bboxes,
        "avg_bbox_count": round(statistics.mean([r["bbox_count"] for r in psm3]), 1) if psm3 else 0,
    }

# Pairwise text similarity (PSM 3)
texts_by_binding = {}
bboxes_by_binding = {}
for b in bindings:
    psm3 = sorted([r for r in by_binding[b] if r["psm"] == 3], key=lambda r: r["image"])
    texts_by_binding[b] = {r["image"]: r["text"] for r in psm3}
    bboxes_by_binding[b] = {r["image"]: r.get("bboxes", []) for r in psm3}

# Common images across all bindings
all_images = set()
for b in bindings:
    all_images |= set(texts_by_binding[b].keys())
common_images = sorted(all_images)

sim_matrix = {}
iou_matrix = {}
for b1 in bindings:
    sim_matrix[b1] = {}
    iou_matrix[b1] = {}
    for b2 in bindings:
        sims = []
        ious = []
        for img in common_images:
            t1 = texts_by_binding[b1].get(img, "")
            t2 = texts_by_binding[b2].get(img, "")
            if t1 and t2:
                sims.append(similarity(t1, t2))
            bb1 = bboxes_by_binding[b1].get(img, [])
            bb2 = bboxes_by_binding[b2].get(img, [])
            if bb1 and bb2:
                ious.append(avg_bbox_iou(bb1, bb2))
        sim_matrix[b1][b2] = round(statistics.mean(sims), 4) if sims else 0.0
        iou_matrix[b1][b2] = round(statistics.mean(ious), 4) if ious else 0.0

# Write summary.md
with open(OUT_DIR / "summary.md", "w") as f:
    f.write("# OCR Benchmark Summary\n\n")
    f.write(f"**Images tested:** {len(common_images)}  \n")
    f.write(f"**Runs per image:** 3 (median taken)  \n")
    f.write(f"**Bindings tested:** {', '.join(bindings)}  \n\n")

    f.write("## Per-Binding Results (PSM 3)\n\n")
    f.write("| Binding | Images | Median ms | Mean ms | Min ms | Max ms | P95 ms | Bboxes | Avg Bbox Count |\n")
    f.write("|---------|--------|-----------|---------|--------|--------|--------|--------|----------------|\n")
    for b in bindings:
        s = stats[b]
        bbox_str = "Yes" if s["has_bboxes"] else "**No**"
        f.write(f"| {b} | {s['images']} | {s['median_ms']} | {s['mean_ms']} | {s['min_ms']} | {s['max_ms']} | {s['p95_ms']} | {bbox_str} | {s['avg_bbox_count']} |\n")

    f.write("\n## Text Similarity Matrix (PSM 3)\n\n")
    f.write("Normalized Levenshtein similarity (1.0 = identical output)\n\n")
    f.write("| | " + " | ".join(bindings) + " |\n")
    f.write("|" + "---|" * (len(bindings) + 1) + "\n")
    for b1 in bindings:
        row = [f"{sim_matrix[b1].get(b2, 0):.3f}" for b2 in bindings]
        f.write(f"| **{b1}** | " + " | ".join(row) + " |\n")

    if any(iou_matrix[b1][b2] > 0 for b1 in bindings for b2 in bindings if b1 != b2):
        f.write("\n## Bounding Box IoU Matrix\n\n")
        bbox_bindings = [b for b in bindings if stats[b]["has_bboxes"]]
        f.write("| | " + " | ".join(bbox_bindings) + " |\n")
        f.write("|" + "---|" * (len(bbox_bindings) + 1) + "\n")
        for b1 in bbox_bindings:
            row = [f"{iou_matrix[b1].get(b2, 0):.3f}" for b2 in bbox_bindings]
            f.write(f"| **{b1}** | " + " | ".join(row) + " |\n")

    f.write("\n## Recommendation\n\n")
    # Score each binding
    scored = []
    for b in bindings:
        s = stats[b]
        # Criteria: bbox support (required), text accuracy vs pytesseract, latency, build complexity
        has_bbox = 1.0 if s["has_bboxes"] else 0.0
        text_sim = sim_matrix.get("pytesseract", {}).get(b, 0.0)
        # Normalize latency to 0-1 (lower is better)
        max_lat = max(stats[bb]["median_ms"] for bb in bindings) or 1
        lat_score = 1.0 - (s["median_ms"] / max_lat) if max_lat > 0 else 0
        # Build complexity: tesseract_rs > leptess > pytesseract > tesseract_js (all need system deps in practice)
        build_score = {"tesseract_rs": 0.6, "leptess": 0.7, "pytesseract": 0.8, "tesseract_js": 0.5}.get(b, 0.5)

        total = has_bbox * 0.35 + text_sim * 0.30 + lat_score * 0.25 + build_score * 0.10
        scored.append((b, total, has_bbox, text_sim, lat_score, s["median_ms"]))

    scored.sort(key=lambda x: -x[1])

    f.write(f"**Recommended binding: `{scored[0][0]}`**\n\n")
    f.write("| Rank | Binding | Score | Bbox | Text Sim | Latency ms | Latency Score |\n")
    f.write("|------|---------|-------|------|----------|------------|---------------|\n")
    for i, (b, score, has_bbox, text_sim, lat_score, lat_ms) in enumerate(scored):
        bbox_str = "Yes" if has_bbox else "No"
        f.write(f"| {i+1} | **{b}** | {score:.3f} | {bbox_str} | {text_sim:.3f} | {lat_ms} | {lat_score:.3f} |\n")

    f.write("\n### Decision Criteria (weighted)\n\n")
    f.write("1. **Bbox support (35%)** — required for OCR-anchored grid detection (must find '12 AM' and '60' positions)\n")
    f.write("2. **Text accuracy (30%)** — similarity to pytesseract baseline (for title/total extraction)\n")
    f.write("3. **Latency (25%)** — lower is better\n")
    f.write("4. **Build complexity (10%)** — self-contained > system deps\n")

print(f"Written: {OUT_DIR / 'summary.md'}")

# Write similarity_matrix.md (same as in summary but standalone)
with open(OUT_DIR / "similarity_matrix.md", "w") as f:
    f.write("# OCR Binding Pairwise Comparison\n\n")

    # Per-image comparison table
    f.write("## Per-Image Text Output (PSM 3, first 80 chars)\n\n")
    f.write("| Image | " + " | ".join(bindings) + " |\n")
    f.write("|-------|" + "---|" * len(bindings) + "\n")
    for img in common_images[:10]:
        short = img[:30] + "..." if len(img) > 30 else img
        cols = []
        for b in bindings:
            t = texts_by_binding[b].get(img, "N/A")[:80].replace("|", "\\|").replace("\n", " ")
            cols.append(t)
        f.write(f"| {short} | " + " | ".join(cols) + " |\n")

print(f"Written: {OUT_DIR / 'similarity_matrix.md'}")

# Also save raw stats as JSON
with open(OUT_DIR / "results.json", "w") as f:
    json.dump({
        "stats": stats,
        "similarity_matrix": sim_matrix,
        "iou_matrix": iou_matrix,
        "scoring": [{"binding": b, "total_score": s, "has_bbox": hb, "text_sim": ts, "lat_score": ls, "median_ms": ms} for b, s, hb, ts, ls, ms in scored],
        "config": {"images": len(common_images), "runs": 3, "psm_modes": [3, 6], "bindings": bindings},
    }, f, indent=2)
print(f"Written: {OUT_DIR / 'results.json'}")
