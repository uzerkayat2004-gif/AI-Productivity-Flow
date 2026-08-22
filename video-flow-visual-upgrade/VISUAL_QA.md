# VISUAL_QA — quality checks

Tool: `visual_qa.py` (this directory). Deterministic, ffmpeg/PIL-based.

```
python visual_qa.py <video.mp4> <out_prefix> [--frames N]
```

Outputs `<prefix>.sheet.jpg` (contact sheet) and prints:

- **probe** — duration, resolution, codec, size (must be h264; pipeline
  normalizes to 1920x1080 yuv420p).
- **frame_contrast_avg** — mean intra-frame contrast over 12 sampled frames
  (weak-hierarchy / washed-out detector).
- **frame_to_frame_change_avg** — mean absolute change between consecutive
  samples (visual monotony detector; baseline A ≈ 278 vs upgraded ≈ 527–558).
- **monotony_flag** — change below 3.0 threshold.
- **structure_repetition** — treatment sequence + `max_consecutive` from the
  sibling `creative-direction.json` (repetition detector, mission §42).

## Checklist applied per finished video (mission §41)

- excessive text → label caps enforced at authoring; VLM review of sheet
  confirms text/animation proportion;
- repeated layouts → structure_repetition + VLM sheet review;
- clipping / overlap / alignment / empty space → sheet inspection (A had
  consistent margins; C frames aligned to the vfd-stage grid);
- captions obscuring content → captions render in the existing lower band,
  authored stages keep the lower band clear by design;
- low contrast → frame_contrast_avg (C 2601 vs A 1872);
- unsupported glyphs → narration/labels ASCII-normalized at authoring;
- visual/narration mismatch → labels are drawn from the same storyboard
  sentences the narrator reads.

AI/VLM review supplements the deterministic metrics (used on A/B/C sheets);
it is not the only validation — every claim above has a numeric counterpart.

## Sheets in this directory

- `baseline-A.sheet.jpg` · `full-fidelity-B.sheet.jpg` · `variant-C.sheet.jpg`
- driving-test sheet: `driving-D.sheet.jpg` (see AB_BENCHMARK.md)
