# Browser detection model

Place the validated one-class ONNX stamp detector here as:

`stamp-detector.onnx`

Expected input: float32 `[1,3,640,640]`, RGB, values 0–1, letterboxed.

The Browser Beta automatically detects whether the model exists. If it is unavailable or inference fails, `stamp-detector.mjs` falls back to `heuristic-stamp-detector.mjs` so the application remains usable.

Do not add an unvalidated model to production. See `training/stamp-detector/README.md` for the acceptance gate.
