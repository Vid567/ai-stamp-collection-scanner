# AI Stamp Collection Scanner

**AI-Assisted Stamp Inventory**

Turn your stamp collection into a clear digital inventory. Upload collection photos, create structured and photo-linked records, keep track of every item and organise stamps that may deserve further research. The Browser Beta runs locally in your browser, and you remain in control of every detail.

![AI Stamp Collection Scanner](assets/marketing/premium/README-Banner-1600x500.jpg)

## What it does

- Runs as a private Browser Beta at [AI Stamp Collection Scanner](https://vid567.github.io/ai-stamp-collection-scanner/beta/).
- Accepts one or more photos and creates an editable, photo-linked inventory workflow.
- Keeps photos and inventory details local to the browser.
- Exports the reviewed inventory to Excel or CSV.
- Marks unknown details for review instead of presenting uncertain information as fact.

The Browser Beta does not determine rarity, value, authenticity or an exact catalogue identity. It supports collector judgement; it does not replace it.

## Optional local toolkit

- Uses a photo-first workflow for album and stockbook pages.
- Produces structured, paste-ready Inventory rows with an AI helper prompt.
- Keeps every populated row linked through a static Record ID, Photo Number and Original Filename.
- Includes an Images worksheet for a stamp crop or source-photo thumbnail, with a clear filename fallback when no image can be embedded.
- Records suggested identification and confidence level.
- Reconciles visible photo counts against captured quantities.
- Optionally creates traceable crops and embedded Excel thumbnails locally.
- Keeps every enriched row linked to its numbered source photograph and filename.
- Flags classics, overprints, uncertain IDs and physical checks for research.
- Calculates collection totals from estimated per-stamp values.

AI output is a starting point—not authentication, guaranteed identification or professional valuation.

## Download

[Download the complete Version 2.2 toolkit](downloads/AI-Stamp-Collection-Scanner-v2.2.zip)

## Included

- Reusable Excel inventory workbook
- Filled sample workbook
- AI Photo-ID prompt
- Photo Linking & Images addendum
- User Guide
- Country and inscription cheat-sheet
- Quick Start Card
- Google Sheets notes
- Optional local Phase 1 traceability processor
- Crop, thumbnail and Excel-image validation
- AI-assisted research fields with independent confidence scores
- Local image-quality analysis and duplicate candidates
- Collection Summary worksheet

## Optional traceability workflow

Version 2.1 keeps the original prompt-to-Excel workflow and adds an optional local processor. The Phase 1 prompt requests normalized stamp boxes. The processor then retains source photos locally, creates lossless crops and 256 x 256 thumbnails, embeds one thumbnail per Inventory row and writes a validation report.

See [the Phase 1 guide](docs/PHASE-1-GUIDE.md). This feature requires Python and Pillow; it does not add or replace an AI model.

## Optional collection review workflow

Phase 2 builds on the same processor and workbook. The external vision-AI supplies cautious identification suggestions; local code measures crop quality, reports visually similar candidates, applies conservative recommendations and produces collection statistics. See [the Phase 2 guide](docs/PHASE-2-GUIDE.md).

## Website

The repository is ready for GitHub Pages. Publish from the `main` branch and repository root.

The core workflow remains a static Excel-and-prompt toolkit. Visual references can still be supplied by the AI tool or pasted manually. The optional local processor automates crops, thumbnails and workbook embedding when normalized bounding boxes are available.

## Product language

Use: **AI-assisted**, **suggested identification**, **confidence level**, **needs research**, **potentially interesting**.

Do not claim guaranteed identification, rarity, valuation or selling price.

## Content Creator

Use the [AI Stamp Scanner Content Creator](https://vid567.github.io/ai-stamp-collection-scanner/content-creator.html) to plan, copy and track the 25 prepared Threads posts. Planning data stays in the browser; the tool does not automatically publish to Threads.

## Licence

The downloadable toolkit is licensed for personal use. See `LICENSE.txt` inside the release package.
