# Changelog

> **Version-line note:** entries 2.0–2.2 below describe the legacy pre-Browser-Beta toolkit. They are not newer releases of Browser Beta v1.0. See [LEGACY-TOOLKIT.md](LEGACY-TOOLKIT.md).

## Browser Beta v1.0 — 2026-08-14

- Kept every separately detected physical stamp as a separate inventory record, including visually identical stamps.
- Clarified that production uses local heuristic photo detection with manual review; no validated ONNX model is active.
- Corrected privacy wording to distinguish local photo/inventory processing from anonymous usage analytics.
- Made the Browser Beta documentation hierarchy and legacy toolkit status explicit.
- Added Browser Beta regression tests for physical-stamp grouping, formats, limits, numbering, exports and detector status.

## 2.2 - 2026-07-31

- Added conservative AI-assisted identification and independent field confidence columns.
- Added deterministic crop-quality scoring and rescan recommendations.
- Added perceptual duplicate-candidate reporting without automatic merging.
- Added a Collection Summary worksheet and JSON collection statistics.
- Added conditional confidence, review and duplicate indicators.
- Preserved the existing external vision-AI, crop, thumbnail, traceability and Excel workflows.

## 2.1 - 2026-07-31

- Added static `record_id`, `photo_number`, `original_filename`, `photo_references`, and `stamp_image_reference` fields to Inventory.
- Added Photo Number to Per photo and Progress.
- Added an Images worksheet linked by Record ID and Photo Number, with room for a crop or thumbnail and an explicit fallback.
- Updated the AI Photo-ID prompt for 27-column tab-separated output and stable numbering across 20 or more uploads.
- Added guidance for multiple stamps per photo and one stamp shown in multiple photos.
- Updated website and package documentation without changing analytics configuration.
- Added an optional local traceability processor that preserves the existing 27-column workflow.
- Added lossless crops, centered 256 x 256 thumbnails and one embedded thumbnail per Inventory row.
- Added normalized bounding-box and numeric confidence fields without replacing the existing AI helper.
- Added automatic integrity validation for photos, crops, thumbnails, unique IDs and workbook row counts.

## 2.0 - 2026-07-29

- Released the cleaned reusable workbook, filled sample, five-tab workflow and matching AI prompt.
