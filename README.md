# AI Stamp Collection Scanner — Browser Beta v1.0

Turn stamp collection photos into a structured, editable inventory in a modern browser. The current product line is the hosted **Browser Beta v1.0**.

[Open the Browser Beta](https://vid567.github.io/ai-stamp-collection-scanner/)

![AI Stamp Collection Scanner](assets/marketing/premium/README-Banner-1600x500.jpg)

## Current production behavior

- Browser-only: no Python, terminal, installation, account or AI key is required.
- Uses local photo-based detection to propose one inventory record for each detected physical stamp region.
- Keeps separately visible stamps as separate records, including visually identical stamps.
- Supports JPG/JPEG, PNG and WebP, up to 20 photos per inventory.
- Keeps photo blobs and draft inventory data in browser storage and supports reload recovery while that storage remains available.
- Exports the reviewed 16-column inventory to Excel or CSV; photos are referenced by text and are not embedded.
- Preserves manual add, edit, duplicate, delete and source-photo reassignment controls.

The production build currently uses the validated **heuristic fallback detector**. The repository contains an ONNX adapter, but no production ONNX model or ONNX Runtime bundle is deployed. Do not describe model-based identification as active.

The scanner does not guarantee that every stamp will be found. It does not automatically identify countries or catalogue numbers, and it does not determine value, rarity or authenticity. Automatic results require manual review.

## Privacy and analytics

Stamp photos and inventory data are processed locally in the browser and are not uploaded for stamp identification. Anonymous usage analytics may be collected through the existing project GA4 configuration to help improve the beta.

## Start and documentation

### English

- [English test page](https://vid567.github.io/ai-stamp-collection-scanner/beta-test-en.html)
- [English scanner](https://vid567.github.io/ai-stamp-collection-scanner/beta/scanner-en.html)
- [Quick Start](beta/docs/en/quick-start.html)
- [User Guide](beta/docs/en/user-guide.html)
- [FAQ](beta/docs/en/faq.html)
- [Troubleshooting](beta/docs/en/troubleshooting.html)

### Nederlands

- [Nederlandse testpagina](https://vid567.github.io/ai-stamp-collection-scanner/beta-test-nl.html)
- [Nederlandse scanner](https://vid567.github.io/ai-stamp-collection-scanner/beta/scanner-nl.html)
- [Snel starten](beta/docs/nl/snel-starten.html)
- [Gebruikershandleiding](beta/docs/nl/gebruikershandleiding.html)
- [Veelgestelde vragen](beta/docs/nl/veelgestelde-vragen.html)
- [Problemen oplossen](beta/docs/nl/problemen-oplossen.html)

The language chooser also links to Spain Spanish, US Spanish, French, German, Brazilian Portuguese and Simplified Chinese versions.

## Detector validation status

The repository currently contains 245 reviewed bounding boxes across nine annotated source images. Dense pages remain underrepresented and several source pages are still pending or in review. In particular, stamp-source-10 has not completed review. This is not sufficient evidence to promote an ONNX model.

See [training/stamp-detector/README.md](training/stamp-detector/README.md) and [annotation-status.csv](training/stamp-detector/annotation-status.csv).

## Legacy / pre-Browser-Beta toolkit

The root-level workbook, Python tools, Phase 1/Phase 2 prompts, PDFs and downloads/AI-Stamp-Collection-Scanner-v2.x.zip belong to an earlier toolkit product line. Toolkit versions 2.0–2.2 are historical and are **not** Browser Beta releases or current Gumroad delivery files.

See [LEGACY-TOOLKIT.md](LEGACY-TOOLKIT.md) before using any of that material. The obsolete Stamp-Inventory-Toolkit_v1.0.zip is not a release source for this application.

## Release identity

The canonical product is the hosted Browser Beta. A GitHub tag or release named browser-beta-v1.0 may document the tested hosted release, but it must not attach or present historical toolkit ZIPs as the browser application.
