# Grid Detection System

## Overview

iOS Screen Time screenshots have consistent grid positions within each resolution. This document tracks our findings and approach for auto-detecting the plot region.

## Known Resolution Grid Coordinates

From manual labeling of reference images:

| Resolution | Grid Position (x, y) | Grid Size (w × h) | Cluster |
|------------|---------------------|-------------------|---------|
| 640×1136 | (32, 274) | 511×180 | A |
| 750×1334 | (65, 669) | 557×181 | B |
| 750×1624 | (64, 446) | 548×180 | C |
| 828×1792 | (80, 452) | 601×180 | D |
| 848×2266 | (72, 394) | 640×181 | E |
| 858×2160 | (84, 395) | 639×180 | E |
| 896×2048 | (73, 387) | 687×180 | F |
| 906×2160 | (83, 387) | 687×180 | F |
| 960×2079 | (48, 615) | 769×271 | G (tall) |
| 980×2160 | (73, 386) | 771×181 | H |
| 990×2160 | (83, 387) | 771×180 | H |
| 1000×2360 | (74, 394) | 788×182 | I |
| 1028×2224 | (72, 387) | 820×180 | J |
| 1028×2388 | (73, 394) | 819×180 | J |
| 1170×2532 | (96, 642) | 883×271 | K (tall) |

### Grid Size Clusters

Resolutions that share the same grid dimensions (likely same iOS device/scale factor):

| Cluster | Grid Size | Resolutions |
|---------|-----------|-------------|
| E | ~640×180 | 848×2266, 858×2160 |
| F | ~690×180 | 896×2048, 906×2160 |
| H | ~770×180 | 980×2160, 990×2160 |
| J | ~820×180 | 1028×2224, 1028×2388 |

### Height Variants

- **~180px height**: Standard layout (most resolutions)
- **~270px height**: Taller layout (960×2079, 1170×2532) - possibly different iOS version or display scale

## Lookup Table

Stored in `reference_images/grid_lookup.json`:

```json
{
  "848x2266": {
    "x": 72,
    "y": 394,
    "width": 640,
    "height": 181
  },
  ...
}
```

## Unknown Resolution Handling

For resolutions not in the lookup table, we need to detect the grid position.

### OCR-Based Refinement (Secondary)

Use hour labels ("12AM", "6AM", "12PM", "6PM") as anchor points:
- Start with an initial grid estimate
- Apply small shifts and measure OCR total consistency
- Optimize until OCR total stabilizes

This is a refinement step, not primary detection.

### Non-OCR Detection (Primary) - TBD

Need to find visual invariants that don't rely on OCR or blue bars (bars may be absent).

See "Invariant Analysis" section below.

## Visual Features of the Plot Region

- **Background**: Light gray (#F2F2F7 or similar iOS system gray)
- **Bars**: Blue (#007AFF or similar iOS blue), vertical, evenly spaced (24 bars for 24 hours)
- **Hour labels**: "12AM", "6AM", "12PM", "6PM" below plot, dark text
- **Grid lines**: Faint horizontal lines at usage intervals

## Implementation Status

- [x] Manual grid labeling for 15 resolutions
- [x] Grid lookup JSON created
- [ ] Backend integration for auto-apply on known resolutions
- [ ] Detection algorithm for unknown resolutions
- [ ] Validation against existing verified annotations

## Reference Files

- `reference_images/grid_lookup.json` - Coordinate lookup table
- `reference_images/{resolution}/` - Sample images per resolution
- `reference_images/{resolution}/*GRID.png` - Cropped grid regions used for labeling

## Invariant Analysis

Looking for visual features that are ALWAYS present regardless of usage data.

### Resolution-Based Invariants (Found)

| Property | Finding |
|----------|---------|
| Grid position | Consistent within same resolution |
| Grid size | Clusters exist across similar resolutions |
| Height | Two variants: ~180px (standard) and ~270px (tall) |

### Structural Invariants (To Investigate)

Things that should be constant across ALL screenshots:

1. **Horizontal grid lines** - Faint lines at fixed intervals (e.g., 1h, 2h marks)
2. **Plot boundary edges** - Sharp transition between plot area and surrounding UI
3. **Aspect ratio of plot** - Width:height ratio may be consistent
4. **Margins/padding** - Distance from screen edge to plot may follow iOS HIG
5. **Bottom axis line** - Solid line separating plot from hour labels
6. **UI elements above/below** - "Daily Average" text, day selector, etc.

### Color Invariants (To Investigate)

1. **Plot background color** - iOS system gray (light mode) or dark gray (dark mode)
2. **Grid line color** - Consistent faint gray
3. **Axis line color** - Darker than grid lines

### Ratio Invariants (To Investigate)

1. **grid_width / image_width** - Is this consistent?
2. **grid_x / image_width** - Left margin ratio
3. **grid_y / image_height** - Top margin ratio

### Next Steps

1. Analyze the labeled grids to find ratio patterns
2. Look for edge/line detection opportunities
3. Test if iOS HIG defines these margins
