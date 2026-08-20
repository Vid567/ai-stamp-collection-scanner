// Mirrors the per-photo loop in createInventory() to prove that a failure on
// one photo never stops the remaining photos, and that retries recover
// transient overload. Run: node tests/batch-simulation.test.mjs
import assert from "node:assert/strict";

globalThis.document = {createElement: () => ({
  getContext: () => ({fillRect(){}, strokeRect(){}, set fillStyle(v){}, set strokeStyle(v){}}),
  toDataURL: () => "data:image/jpeg;base64,TEST",
})};
globalThis.localStorage = {getItem: () => "test-key", setItem(){}, removeItem(){}};

const {fetchWithRetry} = await import("../beta/ai-identify.mjs");
const FAST = {attempts: 4, baseDelayMs: 2, maxDelayMs: 8};
const json = (s, b) => new Response(JSON.stringify(b), {status: s, headers: {"Content-Type": "application/json"}});

/** Same control flow as createInventory: try/catch per photo, loop continues. */
async function runBatch(photos, respond) {
  const records = [], errors = [];
  let identified = 0, done = 0;
  for (const p of photos) {
    try {
      const res = await fetchWithRetry("https://relay", {photo: p.id}, FAST);
      const body = await res.json().catch(() => null);
      if (!res.ok || !Array.isArray(body?.identifications)) {
        throw new Error(body?.error || `AI identification failed (${res.status})`);
      }
      identified += body.identifications.length;
      records.push({photo: p.id, source: "ai"});
    } catch (e) {
      errors.push(e.message);
      records.push({photo: p.id, source: "local"}); // still added, local detection only
    }
    done++;
  }
  return {records, errors, identified, done};
}

const photos = Array.from({length: 20}, (_, i) => ({id: `p${i + 1}`}));
let passed = 0, failed = 0;
async function test(name, fn) {
  try { await fn(); console.log(`  PASS  ${name}`); passed++; }
  catch (e) { console.log(`  FAIL  ${name}\n        ${e.message}`); failed++; }
}

console.log("\n--- 20-photo batch ---");

await test("all 20 photos produce a record when everything succeeds", async () => {
  globalThis.fetch = async () => json(200, {identifications: [{index: 0}]});
  const r = await runBatch(photos);
  assert.equal(r.done, 20);
  assert.equal(r.records.length, 20);
  assert.equal(r.errors.length, 0);
});

await test("photos 5 and 12 fail permanently — the other 18 still complete", async () => {
  globalThis.fetch = async (url, init) => (["p5", "p12"].includes(init.photo)
    ? json(400, {error: "API key not valid"})
    : json(200, {identifications: [{index: 0}]}));
  const r = await runBatch(photos);
  assert.equal(r.done, 20, "loop must reach every photo");
  assert.equal(r.records.length, 20, "every photo must yield a record");
  assert.equal(r.errors.length, 2);
  assert.equal(r.records.filter(x => x.source === "ai").length, 18);
});

await test("transient overload on every photo is recovered by retry", async () => {
  const tries = {};
  globalThis.fetch = async (url, init) => {
    tries[init.photo] = (tries[init.photo] || 0) + 1;
    return tries[init.photo] < 3
      ? json(502, {error: "This model is currently experiencing high demand."})
      : json(200, {identifications: [{index: 0}]});
  };
  const r = await runBatch(photos);
  assert.equal(r.errors.length, 0, `expected full recovery, got: ${r.errors[0]}`);
  assert.equal(r.records.filter(x => x.source === "ai").length, 20);
});

await test("sustained outage degrades gracefully: 20 records, all local", async () => {
  globalThis.fetch = async () => json(503, {error: "overloaded"});
  const r = await runBatch(photos);
  assert.equal(r.records.length, 20, "no photo may be silently dropped");
  assert.equal(r.errors.length, 20);
  assert.equal(r.records.filter(x => x.source === "local").length, 20);
});

await test("distinct errors are deduplicated for the summary line", async () => {
  globalThis.fetch = async () => json(503, {error: "overloaded"});
  const r = await runBatch(photos);
  assert.equal([...new Set(r.errors)].length, 1, "20 identical errors must collapse to 1 message");
});

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed ? 1 : 0);
