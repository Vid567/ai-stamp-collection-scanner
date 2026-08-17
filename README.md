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

The scanner does not guarantee that every stamp will be found, and it does not determine value, rarity or authenticity. Automatic results (both region detection and, if enabled, AI identification) always require manual review — nothing is ever auto-confirmed.

## Optional: real AI identification (bring your own free key)

By default the scanner only proposes *where* stamps are on a photo; country, period, denomination etc. are left as "Unknown" for manual entry, same as always. As an **opt-in** addition, each language page now has an "AI stamp identification" box where a visitor can paste their own free Google Gemini API key (https://aistudio.google.com/apikey — no credit card required). If they do, `beta/ai-identify.mjs` fills those fields in automatically via a small, secret-free Cloudflare Worker relay (`worker/gemini-relay.js`).

This is deliberately **bring-your-own-key**, not a site-wide AI feature paid for by the site owner: every visitor's usage draws only on their own free Gemini quota, so no amount of traffic ever costs the person running this site anything, and one visitor's use can never exhaust another's. The relay worker exists only because Gemini's API doesn't support being called directly from a browser (no CORS headers) — it holds no API key of its own and needs no secret configuration, just `wrangler deploy`. See [worker/README.md](worker/README.md) for the one-time setup, then set `AI_RELAY_ENDPOINT` in `beta/ai-identify.mjs`.

Until a visitor enters their own key (and the relay is deployed), every language page behaves exactly as documented above — local detection only, nothing sent anywhere. Once a key is entered, "Create inventory" also calls the relay (one request per uploaded photo, using that visitor's key) and fills country/period/denomination/currency/colour/subject/usage/confidence from the AI's reading of each detected region, marked with status "AI suggestion" for review; it also flags regions that turn out to be empty pre-printed album slots rather than mounted stamps.

## Privacy and analytics

Stamp photos and inventory data are processed locally in the browser. They are not uploaded anywhere for stamp identification unless a visitor pastes their own Gemini API key into the optional AI box, in which case a resized copy of each uploaded photo is sent (via the relay worker) to Google's Gemini API using that visitor's own key, for that identification request only. The key itself is stored only in that visitor's own browser. Anonymous usage analytics may be collected through the existing project GA4 configuration to help improve the beta.

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
