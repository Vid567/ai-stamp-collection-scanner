# AI Stamp Collection Scanner

**AI-Assisted Inventory & Research Toolkit**

Turn photos of a stamp collection into a structured inventory and identify which items may need further research.

![AI Stamp Collection Scanner](assets/marketing/premium/README-Banner-1600x500.jpg)

## What it does

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

[Download the complete Version 2.1 toolkit](downloads/AI-Stamp-Collection-Scanner-v2.1.zip)

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

## Optional traceability workflow

Version 2.1 keeps the original prompt-to-Excel workflow and adds an optional local processor. The Phase 1 prompt requests normalized stamp boxes. The processor then retains source photos locally, creates lossless crops and 256 x 256 thumbnails, embeds one thumbnail per Inventory row and writes a validation report.

See [the Phase 1 guide](docs/PHASE-1-GUIDE.md). This feature requires Python and Pillow; it does not add or replace an AI model.

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
