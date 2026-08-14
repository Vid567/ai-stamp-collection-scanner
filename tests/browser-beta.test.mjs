import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { regionsToPhysicalStampGroups } from '../beta/detection-result.mjs';
import { INVENTORY_FIELDS, createRecord, exportRows, nextRecordId, partitionPhotoFiles, photoNumber, toCsv } from '../beta/scanner-core.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const image = (name, type) => ({name, type});

test('each visible physical region becomes its own quantity-one group', () => {
  const identical = {width: 100, height: 120, hash: 'same', colour: [1, 2, 3]};
  for (const count of [1, 2, 3]) {
    const regions = Array.from({length: count}, (_, index) => ({...identical, x: index * 120}));
    const groups = regionsToPhysicalStampGroups(regions);
    assert.equal(groups.length, count);
    assert.deepEqual(groups.map(group => group.quantity), Array(count).fill(1));
    assert.ok(groups.every(group => group.matches.length === 1));
  }
});

test('photo uploads accept JPG, PNG and WebP and enforce the 20-photo limit', () => {
  const files = [image('a.jpg', 'image/jpeg'), image('b.png', 'image/png'), image('c.webp', 'image/webp'), image('d.gif', 'image/gif')];
  const result = partitionPhotoFiles(files, 18, 20);
  assert.deepEqual(result.accepted.map(file => file.name), ['a.jpg', 'b.png']);
  assert.deepEqual(result.unsupported.map(file => file.name), ['d.gif']);
  assert.equal(result.overLimit, 1);
});

test('photo and record numbering remain deterministic across batches', () => {
  assert.deepEqual([0, 1, 2].map(photoNumber), ['Photo 001', 'Photo 002', 'Photo 003']);
  const first = {id: 'a', number: photoNumber(0), name: 'same.jpg'};
  const second = {id: 'b', number: photoNumber(1), name: 'same.jpg'};
  const records = [createRecord(first, 1), createRecord(first, 2)];
  assert.equal(nextRecordId(first, records), 'P001-003');
  assert.equal(nextRecordId(second, records), 'P002-001');
});

test('Excel and CSV rows retain the 16 Browser Beta fields', () => {
  const photo = {id: 'a', number: 'Photo 001', name: 'stamp.jpg'};
  const rows = exportRows([createRecord(photo, 1)]);
  assert.equal(INVENTORY_FIELDS.length, 16);
  assert.deepEqual(Object.keys(rows[0]), INVENTORY_FIELDS);
  const csv = toCsv([createRecord(photo, 1)]);
  assert.ok(csv.startsWith('\uFEFF'));
  for (const field of INVENTORY_FIELDS) assert.ok(csv.includes('"' + field + '"'));
});

test('production remains on the documented heuristic fallback until a validated model exists', () => {
  assert.equal(existsSync(resolve(root, 'beta/models/stamp-detector.onnx')), false);
  const detector = readFileSync(resolve(root, 'beta/stamp-detector.mjs'), 'utf8');
  assert.match(detector, /detectHeuristically/);
  assert.match(detector, /heuristic-fallback/);
});

test('reviewed annotation inventory is explicit and internally consistent', () => {
  const lines = readFileSync(resolve(root, 'training/stamp-detector/annotation-status.csv'), 'utf8').trim().split(/\r?\n/).slice(1);
  const reviewed = lines.map(line => line.match(/^([^,]+),([^,]+),([^,]*)/)?.slice(1)).filter(row => row?.[1] === 'reviewed');
  assert.equal(reviewed.length, 9);
  assert.equal(reviewed.reduce((sum, row) => sum + Number(row[2]), 0), 245);
});


test('all eight scanner routes keep upload, inventory, export, documentation and privacy parity', () => {
  const languages = ['en', 'nl', 'es', 'es-us', 'fr', 'de', 'pt-br', 'zh-cn'];
  for (const language of languages) {
    const html = readFileSync(resolve(root, 'beta/scanner-' + language + '.html'), 'utf8');
    const script = readFileSync(resolve(root, 'beta/scanner-' + language + '.js'), 'utf8');
    assert.match(html, /id="photo-input"/);
    assert.match(html, /id="create-inventory"/);
    assert.match(html, /id="export-xlsx"/);
    assert.match(html, /id="export-csv"/);
    assert.match(html, /docs\//);
    assert.match(html, /analytics|statistieken|estadísticas|statistiques|Nutzungsstatistiken|estatísticas|使用统计/i);
    assert.match(script, /detectStampGroups/);
  }
});

test('authoritative English and Dutch docs state limits and manual review', () => {
  const files = [
    'beta/docs/en/user-guide.html', 'beta/docs/en/faq.html',
    'beta/docs/nl/gebruikershandleiding.html', 'beta/docs/nl/veelgestelde-vragen.html',
  ];
  for (const file of files) {
    const text = readFileSync(resolve(root, file), 'utf8');
    assert.match(text, /20/);
    assert.match(text, /Excel/);
    assert.match(text, /CSV/);
    assert.doesNotMatch(text, /Nothing is uploaded|Er wordt niets naar een server geüpload/);
  }
});

test('legacy toolkit downloads are explicitly classified and not presented as Browser Beta releases', () => {
  const readme = readFileSync(resolve(root, 'README.md'), 'utf8');
  const legacy = readFileSync(resolve(root, 'LEGACY-TOOLKIT.md'), 'utf8');
  assert.match(readme, /Browser Beta v1.0/);
  assert.ok(readme.includes('Legacy / pre-Browser-Beta toolkit'));
  assert.match(legacy, /not the current/);
  assert.match(legacy, /v2.2.zip/);
});


test('local links and referenced scanner assets resolve', () => {
  const htmlFiles = [
    'index.html', ...['en','nl','es','es-us','fr','de','pt-br','zh-cn'].map(language => 'beta/scanner-' + language + '.html'),
    'beta-test-en.html', 'beta-test-nl.html',
    'beta/docs/en/quick-start.html', 'beta/docs/en/user-guide.html', 'beta/docs/en/faq.html', 'beta/docs/en/troubleshooting.html',
    'beta/docs/nl/snel-starten.html', 'beta/docs/nl/gebruikershandleiding.html', 'beta/docs/nl/veelgestelde-vragen.html', 'beta/docs/nl/problemen-oplossen.html',
  ];
  for (const file of htmlFiles) {
    const html = readFileSync(resolve(root, file), 'utf8');
    const base = dirname(resolve(root, file));
    for (const match of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
      const target = match[1].split(/[?#]/)[0];
      if (!target || /^(?:https?:|data:|mailto:)/.test(target)) continue;
      const resolved = resolve(base, target);
      assert.ok(existsSync(resolved), file + ' has missing local target ' + match[1]);
    }
  }
});
