// Client-side glue for real AI stamp identification, "bring your own key" style.
//
// Every visitor uses their OWN free Google Gemini API key (https://aistudio.google.com/apikey
// — no credit card required). The key is stored only in that visitor's own browser
// (localStorage) and is never sent anywhere except, per request, through the small
// relay worker in worker/gemini-relay.js. That worker holds no secrets of its own —
// it exists purely because the Gemini REST API doesn't send CORS headers, so a
// browser calling it directly gets silently blocked even with a valid key. Nobody
// but the key's own owner is ever billed, and one user's usage can never affect
// another user's free quota.
//
// If no key is stored yet, or AI_RELAY_ENDPOINT is left as the placeholder,
// identifyStampGroups() returns null immediately and every locale scanner falls
// back to exactly the local-detection-only behaviour it had before this feature
// existed. See worker/README.md for the (secret-free) deploy walkthrough.
export const AI_RELAY_ENDPOINT = "https://ai-stamp-scanner-gemini-relay.vidcas567.workers.dev";

const API_KEY_STORAGE_KEY = "stampScannerGeminiApiKey";
const MAX_SIDE = 1400;
const JPEG_QUALITY = 0.85;

function isConfigured(endpoint) {
  return Boolean(endpoint) && !/YOUR-WORKER-SUBDOMAIN/.test(endpoint);
}

export function getStoredApiKey() {
  try {
    return (localStorage.getItem(API_KEY_STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function setStoredApiKey(key) {
  try {
    const trimmed = (key || "").trim();
    if (trimmed) localStorage.setItem(API_KEY_STORAGE_KEY, trimmed);
    else localStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    /* localStorage unavailable (private browsing etc.) — AI identification simply stays off */
  }
}

async function toResizedJpegBase64(blob) {
  const bitmap = await createImageBitmap(blob);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close?.();
  const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  return dataUrl.slice(dataUrl.indexOf(",") + 1);
}

/**
 * Ask the relay (and, behind it, the visitor's own Gemini key) about every
 * detected group in one photo.
 * Returns:
 *  - null if there's no stored API key yet, the relay endpoint isn't configured,
 *    or there is nothing to identify — callers should treat this as "feature not
 *    enabled for this visitor right now", not an error.
 *  - an array of identification objects, aligned by array position to `groups`
 * Throws on network/parse/HTTP failure so callers can distinguish "not enabled"
 * from "tried and failed" (e.g. bad key, quota hit) and message the user.
 */
/**
 * Build a tiny throwaway JPEG so validation exercises the real code path.
 * An empty string is rejected by the relay before the key is ever checked,
 * which would make validation meaningless.
 */
function testImageBase64() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#f0e6c8";
  ctx.fillRect(0, 0, 64, 64);
  ctx.strokeStyle = "#333333";
  ctx.strokeRect(8, 8, 48, 48);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
  return dataUrl.slice(dataUrl.indexOf(",") + 1);
}

/**
 * Check a Gemini API key by sending one real (tiny) identification request
 * end to end: browser → relay → Gemini. Returns {ok, status, message} so the
 * caller can show the actual reason instead of a generic failure.
 */
export async function validateApiKey(apiKey, {endpoint = AI_RELAY_ENDPOINT} = {}) {
  if (!isConfigured(endpoint)) return {ok: false, status: 0, message: "Relay endpoint is not configured."};
  if (!apiKey) return {ok: false, status: 0, message: "No key entered."};

  let response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        apiKey,
        image: testImageBase64(),
        mimeType: "image/jpeg",
        lang: "en",
        regions: [{index: 0, x: 0, y: 0, width: 1, height: 1}],
      }),
    });
  } catch (error) {
    return {ok: false, status: 0, message: `Network error: ${error.message}`};
  }

  const raw = await response.text().catch(() => "");
  let payload = null;
  try { payload = JSON.parse(raw); } catch { /* keep raw text */ }

  if (response.ok && Array.isArray(payload?.identifications)) {
    return {ok: true, status: response.status, message: "Key verified against Gemini."};
  }
  const detail = payload?.error || raw.slice(0, 300) || "no detail returned";
  return {ok: false, status: response.status, message: `HTTP ${response.status}: ${detail}`};
}

export async function identifyStampGroups(blob, groups, {endpoint = AI_RELAY_ENDPOINT, apiKey = getStoredApiKey(), lang = "en", signal} = {}) {
  if (!isConfigured(endpoint) || !apiKey || !groups?.length) return null;
  const image = await toResizedJpegBase64(blob);
  const regions = groups.map((group, index) => ({
    index,
    x: group.normalized?.x ?? 0,
    y: group.normalized?.y ?? 0,
    width: group.normalized?.width ?? 0,
    height: group.normalized?.height ?? 0,
  }));
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({apiKey, image, mimeType: "image/jpeg", lang, regions}),
    signal,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.error || `AI identification failed (${response.status})`);
  if (!payload || !Array.isArray(payload.identifications)) throw new Error("AI identification returned an unexpected response");
  return payload.identifications;
}

const KNOWN_USAGE = new Set(["used", "unused", "uncertain"]);
const KNOWN_CONFIDENCE = new Set(["high", "medium", "low"]);

/**
 * Turns one raw identification (relay/Gemini response shape) into canonical,
 * English-keyed fields. Each locale scanner file maps usageKey/confidenceKey to
 * its own on-screen option strings (they differ per language — see scanner-*.js)
 * and merges the rest directly into the record.
 */
export function canonicalIdentificationFields(identification) {
  if (!identification) return null;
  if (identification.is_empty_slot) return {emptySlot: true, aiNotes: identification.notes || ""};
  const denomination = [identification.face_value, identification.value_unit].filter(Boolean).join(" ").trim();
  return {
    emptySlot: false,
    country: identification.country_normalized || identification.country_as_printed || "",
    period: identification.year || "",
    denomination,
    currency: identification.currency || "",
    colour: identification.colour || "",
    subject: identification.theme || "",
    usageKey: KNOWN_USAGE.has(identification.usage) ? identification.usage : "uncertain",
    confidenceKey: KNOWN_CONFIDENCE.has(identification.confidence) ? identification.confidence : "low",
    aiNotes: identification.notes || "",
  };
}
