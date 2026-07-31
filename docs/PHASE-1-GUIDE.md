# Phase 1 - Photo traceability, crops and Excel thumbnails

Phase 1 is an optional local post-processing layer for the existing AI-assisted workflow. It does not replace the AI service, identification prompt or five-tab workbook.

## What it adds

- stable photo numbering in upload order;
- validated bounding boxes from the AI output;
- lossless PNG crops with a 4% safety margin;
- centered 256 x 256 PNG thumbnails without distortion or upscaling;
- locally retained source photographs;
- one embedded thumbnail per populated Inventory row;
- the existing Record ID, Photo Number, Original Filename, photo references and image-reference fields;
- additional thumbnail, bounding-box, coordinate and generated-file fields;
- an automatic JSON validation report.

## Requirements

- Python 3.10 or newer;
- Pillow, installed with `python -m pip install -r requirements.txt`;
- the original photographs;
- tab-separated AI output made with the Phase 1 prompt;
- `Stamp-Inventory-Template.xlsx` from the toolkit.

## Run

```text
python tools/stamp_traceability.py --detections detections.tsv --photos Photos --template Stamp-Inventory-Template.xlsx --output Output
```

The output folder contains:

```text
Output/
  Stamp Inventory.xlsx
  Photos/
  Crops/
  Thumbnails/
  validation-report.json
```

## Bounding boxes

The four `bbox_*` values are normally fractions of the source image:

- `bbox_x`: distance from the left edge;
- `bbox_y`: distance from the top edge;
- `bbox_width`: stamp width;
- `bbox_height`: stamp height.

All values must fall between 0 and 1 and describe the stamp itself. Set `bbox_normalized` to `yes`. The processor corrects EXIF rotation before applying coordinates.

## Existing workflow remains available

If you do not need automatic thumbnails, continue using the existing 27-column version 2.1 prompt and its prepared Images worksheet. The original 22-column version 2.0 template also remains accepted by the processor.

## Important limitation

The external vision AI estimates the bounding boxes. Always visually inspect crops before relying on the workbook. The processor validates coordinates and file relationships, but it cannot prove that an AI-selected box contains the correct stamp.
