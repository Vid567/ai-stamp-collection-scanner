# AI Stamp Collection Scanner — Beta v1.0 User Guide

## Purpose

Create an editable inventory while retaining the connection between every row and its source photograph.

## Photos

The browser accepts JPG/JPEG, PNG and WebP files. Duplicate filenames are safe because each upload receives its own Photo Number. Up to 20 photos can be used in one Beta inventory.

## Inventory

The scanner creates a manual-review row for every uploaded photo. Add or duplicate rows when a photograph contains multiple stamps. All fields remain editable and every record retains its Record ID, Photo Number, Original Filename and Image Reference.

## Recovery and privacy

The current draft is stored locally in the browser using local storage and IndexedDB. Photos are not uploaded. Browser storage can be cleared by the browser or device, so export completed work regularly.

## AI limitation

The browser Beta contains a safe adapter boundary but no connected paid AI service. It never exposes an API key. Unknown information remains marked `Unknown`, `Uncertain` or `Needs review`.

## Export

Excel is the primary export. CSV is provided as a broadly compatible fallback. Images are represented through reliable Photo Number, Original Filename and Image Reference fields; thumbnails are not embedded in the Beta spreadsheet.

