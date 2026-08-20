// Verifies the retry logic added to beta/ai-identify.mjs.
// Run: node tests/retry.test.mjs
import assert from "node:assert/strict";

// The module touches browser globals at import time only inside functions we
// don't call here, but validateApiKey builds a canvas — stub just enough.
globalThis.document = {createElement: () => ({
  getContext: () => ({fillRect(){}, strokeRect(){}, set fillStyle(v){}, set strokeStyle(v){}}),
  toDataURL: () => "data:image/jpeg;base64,TEST",
})};
globalThis.localStorage = {getItem: () => "test-key", setItem(){}, removeItem(){}};

const mod = await import("../beta/ai-identify.mjs");
const {fetchWithRetry, backoffDelay, validateApiKey, RETRY_DEFAULTS} = mod;

// Keep the suite fast: tiny delays, same logic.
const FAST = {attempts: 4, baseDelayMs: 5, maxDelayMs: 20};

const json = (status, body) => new Response(JSON.stringify(body), {
  status, headers: {"Content-Type": "application/json"},
});

let passed = 0, failed = 0;
async function test(name, fn) {
  try { await fn(); console.log(`  PASS  ${name}`); passed++; }
  catch (e) { console.log(`  FAIL  ${name}\n        ${e.message}`); failed++; }
}

console.log("\n--- fetchWithRetry ---");

await test("retries a 502 overload and succeeds on the 3rd attempt", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return calls < 3
      ? json(502, {error: "This model is currently experiencing high demand."})
      : json(200, {identifications: [{index: 0}]});
  };
  const res = await fetchWithRetry("https://x", {}, FAST);
  assert.equal(calls, 3, `expected 3 calls, got ${calls}`);
  assert.equal(res.status, 200);
});

await test("retries 429 rate limiting", async () => {
  let calls = 0;
  globalThis.fetch = async () => (++calls < 2 ? json(429, {error: "quota"}) : json(200, {identifications: []}));
  const res = await fetchWithRetry("https://x", {}, FAST);
  assert.equal(res.status, 200);
  assert.equal(calls, 2);
});

await test("does NOT retry a genuinely bad key (400)", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; return json(400, {error: "API key not valid"}); };
  const res = await fetchWithRetry("https://x", {}, FAST);
  assert.equal(calls, 1, `400 must not be retried, got ${calls} calls`);
  assert.equal(res.status, 400);
});

await test("gives up after the configured number of attempts", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; return json(503, {error: "overloaded"}); };
  const res = await fetchWithRetry("https://x", {}, FAST);
  assert.equal(calls, 4, `expected 4 attempts, got ${calls}`);
  assert.equal(res.status, 503);
});

await test("retries network errors, then throws if all fail", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error("NetworkError"); };
  await assert.rejects(() => fetchWithRetry("https://x", {}, FAST), /NetworkError/);
  assert.equal(calls, 4);
});

await test("reports each retry via onRetry", async () => {
  let calls = 0;
  const seen = [];
  globalThis.fetch = async () => (++calls < 3 ? json(502, {error: "busy"}) : json(200, {identifications: []}));
  await fetchWithRetry("https://x", {}, FAST, (info) => seen.push(info));
  assert.equal(seen.length, 2, `expected 2 retry callbacks, got ${seen.length}`);
  assert.equal(seen[0].reason, "HTTP 502");
  assert.ok(seen[0].delayMs > 0);
});

console.log("\n--- backoffDelay ---");

await test("grows exponentially and respects the ceiling", async () => {
  const d = (n) => backoffDelay(n, null, {baseDelayMs: 1000, maxDelayMs: 20000});
  assert.ok(d(0) >= 1000 && d(0) <= 1300, `attempt 0 out of range: ${d(0)}`);
  assert.ok(d(1) >= 2000 && d(1) <= 2600, `attempt 1 out of range: ${d(1)}`);
  assert.ok(d(9) === 20000, `should cap at max, got ${d(9)}`);
});

await test("honours a Retry-After header", async () => {
  const res = {headers: {get: (k) => (k === "Retry-After" ? "7" : null)}};
  assert.equal(backoffDelay(0, res, {baseDelayMs: 1000, maxDelayMs: 20000}), 7000);
});

console.log("\n--- validateApiKey ---");

await test("survives a transient overload and reports ok", async () => {
  let calls = 0;
  globalThis.fetch = async () => (++calls < 3
    ? json(502, {error: "This model is currently experiencing high demand."})
    : json(200, {identifications: [{index: 0, is_empty_slot: true}]}));
  const r = await validateApiKey("AQ.test", {retry: FAST});
  assert.equal(r.ok, true, `expected ok, got: ${r.message}`);
  assert.equal(calls, 3);
});

await test("still reports a real key failure", async () => {
  globalThis.fetch = async () => json(400, {error: "API key not valid"});
  const r = await validateApiKey("bad", {retry: FAST});
  assert.equal(r.ok, false);
  assert.match(r.message, /API key not valid/);
});

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed ? 1 : 0);
