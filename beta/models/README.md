# Browser detection model

Place the validated one-class ONNX stamp detector here as:

`stamp-detector.onnx`

Expected input: float32 `[1,3,640,640]`, RGB, values 0–1, letterboxed.

The Browser Beta automatically detects whether the model exists. If it is unavailable or inference fails, `stamp-detector.mjs` falls back to `heuristic-stamp-detector.mjs` so the application remains usable.

Production currently has neither this model nor the ONNX Runtime browser bundle. The active production path is therefore the heuristic fallback. Adding a model file alone is not sufficient to activate a release: the runtime bundle, loader, GitHub Pages paths/MIME behavior, browser performance and acceptance metrics must all pass validation.

Do not add an unvalidated model to production. See `training/stamp-detector/README.md` for the acceptance gate.
