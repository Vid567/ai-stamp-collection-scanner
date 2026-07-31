# Phase 2 - AI-Assisted Identification & Research

Phase 2 enriches the existing photo-linked inventory. It does not install or replace an AI model. Identification fields come from the existing external vision-AI workflow and remain clearly labelled as suggestions.

## What runs locally

- crop quality scoring based on detail, contrast, lighting, resolution and clipped edges;
- dominant-colour fallback when the AI output has no colour;
- perceptual similarity comparison across the uploaded collection;
- independent confidence aggregation;
- conservative research recommendations;
- collection statistics and a Collection Summary worksheet;
- JSON research and validation reports.

## What the vision AI supplies

The Phase 2 prompt can supply a likely country, period, theme, category, possible series, denomination, visible text, language and observable visual traits. Every important identification field has its own confidence value. Unsupported fields must stay blank.

## Run

```text
python tools/stamp_traceability.py --detections detections.tsv --photos Photos --template Stamp-Inventory-Template.xlsx --output Output
```

## Outputs

The existing Photos, Crops, Thumbnails and Stamp Inventory.xlsx outputs remain. Phase 2 adds:

- `research-results.json`;
- `collection-summary.json`;
- research columns in Inventory;
- conditional confidence and review indicators;
- a Collection Summary worksheet.

## Duplicate candidates

Similarity is based on a compact perceptual image hash. It can find crops with strongly similar structure, but it cannot prove that two stamps are the same catalogue variety. Candidates are reported and never merged.

## Important limits

Front photographs generally cannot prove watermark, paper, gum, perforation gauge, repairs, authenticity or exact catalogue variety. Colour can also be affected by lighting and camera processing. A recommendation such as Worth Checking means that human research is justified; it is not a value statement.

## Future-ready fields

The Phase 2 result object is separate from the Phase 1 detection object. Catalogue matches, market evidence, reverse-side analysis and user corrections can later be attached without changing crop generation or traceability.
