import test from "node:test";
import assert from "node:assert/strict";
import {createRecord, exportRows, partitionPhotoFiles, photoNumber, toCsv} from "../scanner-core.mjs";

test("photo numbering is stable and zero padded", () => {
  assert.equal(photoNumber(0), "Photo 001");
  assert.equal(photoNumber(19), "Photo 020");
});

test("record preserves complete source traceability", () => {
  const photo = {id: "image-a", number: "Photo 001", name: "album.jpg"};
  const record = createRecord(photo, 1);
  assert.equal(record.id, "P001-001");
  assert.equal(record.photoNumber, "Photo 001");
  assert.equal(record.filename, "album.jpg");
  assert.match(record.imageReference, /Photo 001.*album\.jpg/);
  assert.equal(record.country, "Unknown");
  assert.equal(record.status, "AI not connected — manual review");
});

test("twenty photos produce independent source-linked rows", () => {
  const records = Array.from({length: 20}, (_, index) => {
    const photo = {id: `id-${index}`, number: photoNumber(index), name: index % 2 ? "duplicate.jpg" : `photo-${index}.png`};
    return createRecord(photo, 1);
  });
  assert.equal(new Set(records.map(row => row.photoNumber)).size, 20);
  assert.equal(exportRows(records).length, 20);
});

test("file selection accepts supported formats and rejects unsupported or excess files", () => {
  const files = [
    {name: "a.jpg", type: "image/jpeg"}, {name: "b.png", type: "image/png"},
    {name: "c.webp", type: "image/webp"}, {name: "notes.txt", type: "text/plain"},
  ];
  const result = partitionPhotoFiles(files, 18, 20);
  assert.deepEqual(result.accepted.map(file => file.name), ["a.jpg", "b.png"]);
  assert.equal(result.unsupported[0].name, "notes.txt");
  assert.equal(result.overLimit, 1);
});

test("CSV export keeps corrections, notes and quoted values", () => {
  const record = createRecord({id: "a", number: "Photo 001", name: "one.jpg"}, 1);
  record.country = "Netherlands"; record.notes = 'Blue, marked "used"'; record.status = "User confirmed";
  const csv = toCsv([record]);
  assert.match(csv, /Netherlands/); assert.match(csv, /Blue, marked ""used""/); assert.match(csv, /User confirmed/);
});
