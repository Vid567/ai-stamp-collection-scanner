# Stamp object detector

Browser Beta uses a one-class object detector (`stamp`) when `beta/models/stamp-detector.onnx` is present. Until then it automatically falls back to the heuristic detector.

## Dataset

Use varied real collection photos: single stamps, dense album pages, cancellations, handwritten notes, overlapping material, different backgrounds, rotations, colours and duplicate stamps.

Annotate **every visible physical stamp** with one bounding box and class `stamp`. Do not box handwritten notes, album lines, hinges, envelope areas or empty spaces. Separately visible identical stamps remain separate boxes and separate inventory records; similarity must never merge physical detections.

Recommended split: 70% train / 20% validation / 10% test. Keep near-duplicate photos in the same split to avoid leakage.

Directory layout:

```
training/stamp-detector/dataset/
  images/train/
  images/val/
  images/test/
  labels/train/
  labels/val/
  labels/test/
```

YOLO label format per line: `0 x_center y_center width height`, normalized to 0–1.

## Training

Install Ultralytics in a separate training environment, then train a small detector. Example:

```
yolo detect train data=training/stamp-detector/data.yaml model=yolo11n.pt imgsz=640 epochs=100 patience=20
```

Validate especially on dense album pages. Do not promote a model based only on easy single-stamp photos.

## Export

Export the best model to ONNX with a fixed 640×640 input. Keep raw detection output so the browser adapter can perform NMS:

```
yolo export model=runs/detect/train/weights/best.pt format=onnx imgsz=640 simplify=True nms=False
```

Copy the resulting model to:

`beta/models/stamp-detector.onnx`

The browser adapter first tries WebGPU and automatically falls back to WASM. Photos remain local in the browser.

## Acceptance gate

Before replacing the fallback as the default quality path, test at least:

- single stamp: >= 98% recall;
- sparse album pages: >= 95% recall;
- dense album pages: >= 90% recall;
- false positives on notes/album lines: <= 3%;
- no crashes on JPG, PNG or WebP;
- duplicate grouping is evaluated separately after object detection.

Keep the heuristic fallback until the ONNX model passes these gates.

## Current reviewed ground truth

`annotation-status.csv` currently records 245 reviewed boxes across nine images. Dense source pages remain incomplete, including `stamp-source-10` in review. No ONNX model may be promoted from this repository state alone.
