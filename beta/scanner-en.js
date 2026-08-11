import { createRecord, exportRows, nextRecordId, partitionPhotoFiles, photoNumber, toCsv } from "./scanner-core.mjs";

const MAX_FILES = 20;
const STORAGE_KEY = "stampScannerBetaV1";
const PHOTO_SEQUENCE_KEY = "stampScannerBetaPhotoSequence";
const dbPromise = openDatabase();
let photos = [];
let records = [];
let nextPhotoSequence = readPhotoSequence();

const $ = selector => document.querySelector(selector);
const fields = [
  ["country", "Country / Possible Country"], ["period", "Approximate Period"],
  ["denomination", "Denomination"], ["currency", "Currency"], ["colour", "Main Colour"],
  ["subject", "Subject / Design"], ["usage", "Used / Unused", ["Uncertain", "Used", "Unused"]],
  ["quantity", "Quantity", "number"], ["confidence", "Confidence", ["Needs review", "Low", "Medium", "High", "User confirmed"]],
  ["furtherResearch", "Further Research", ["No", "Yes"]], ["notes", "Collector Notes", "textarea"],
  ["status", "Information Status", ["AI not connected — manual review", "AI suggestion", "User confirmed"]],
];

function readPhotoSequence() {
  const value = Number.parseInt(sessionStorage.getItem(PHOTO_SEQUENCE_KEY) || "1", 10);
  return Number.isFinite(value) && value > 0 ? value : 1;
}

function writePhotoSequence() { sessionStorage.setItem(PHOTO_SEQUENCE_KEY, String(nextPhotoSequence)); }
function photoSequenceFromLabel(label = "") { return Number.parseInt(String(label).replace(/\D/g, ""), 10) || 0; }
function syncPhotoSequenceFromRestoredPhotos() { const highestExisting = Math.max(0, ...photos.map(photo => photoSequenceFromLabel(photo.number))); nextPhotoSequence = Math.max(nextPhotoSequence, highestExisting + 1); writePhotoSequence(); }
function takeNextPhotoNumber() { const number = photoNumber(nextPhotoSequence - 1); nextPhotoSequence += 1; writePhotoSequence(); return number; }

function openDatabase() { return new Promise((resolve, reject) => { const request = indexedDB.open("stampScannerBeta", 1); request.onupgradeneeded = () => request.result.createObjectStore("photos", {keyPath: "id"}); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); }); }
async function storePhoto(photo) { const db = await dbPromise; return new Promise((resolve, reject) => { const tx = db.transaction("photos", "readwrite"); tx.objectStore("photos").put(photo); tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); }); }
async function removeStoredPhotos() { const db = await dbPromise; return new Promise((resolve, reject) => { const tx = db.transaction("photos", "readwrite"); tx.objectStore("photos").clear(); tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); }); }
async function loadStoredPhotos(ids) { const db = await dbPromise; return Promise.all(ids.map(id => new Promise(resolve => { const request = db.transaction("photos").objectStore("photos").get(id); request.onsuccess = () => resolve(request.result); request.onerror = () => resolve(null); }))); }
function saveState() { localStorage.setItem(STORAGE_KEY, JSON.stringify({photoIds: photos.map(p => p.id), records})); }
async function restoreState() { try { const state = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); if (!state) return; photos = (await loadStoredPhotos(state.photoIds || [])).filter(Boolean); records = (state.records || []).filter(record => photos.some(photo => photo.id === record.photoId)); syncPhotoSequenceFromRestoredPhotos(); render(); } catch { showMessage("The previous session could not be restored. You can start a new inventory."); } }
function showMessage(message = "") { $("#messages").textContent = message; }
function newId() { return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`; }

async function addFiles(fileList) {
  const {accepted, unsupported, overLimit} = partitionPhotoFiles(fileList, photos.length, MAX_FILES);
  if (unsupported.length) showMessage(`${unsupported.length} unsupported file(s) were not added. Use JPG, PNG or WebP.`);
  else if (overLimit) showMessage(`This Beta supports up to ${MAX_FILES} photos per inventory.`);
  else showMessage("");
  for (const file of accepted) {
    const id = newId(); const photo = {id, number: takeNextPhotoNumber(), name: file.name, type: file.type, size: file.size, blob: file}; photos.push(photo);
    try { await storePhoto(photo); } catch { showMessage("A photo could not be saved for recovery, but remains available in this session."); }
  }
  if (accepted.length) globalThis.gtag?.("event", "photos_selected", {photo_count: accepted.length});
  saveState(); render();
}

function imageUrl(photo) { return URL.createObjectURL(photo.blob); }
function revokeImageUrl(image, url) { image.onload = image.onerror = () => URL.revokeObjectURL(url); }
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character])); }

function renderPhotos() {
  $("#photo-grid").innerHTML = photos.map(photo => `<article class="photo-card"><img data-photo="${photo.id}" alt="Preview of ${escapeHtml(photo.name)}"><div><strong>${photo.number}</strong><small title="${escapeHtml(photo.name)}">${escapeHtml(photo.name)}</small></div></article>`).join("");
  document.querySelectorAll("[data-photo]").forEach(image => { const photo = photos.find(item => item.id === image.dataset.photo); const url = imageUrl(photo); image.src = url; revokeImageUrl(image, url); });
}

function createField(record, [key, label, type]) {
  const wrapper = document.createElement("div"); wrapper.className = `field ${key === "notes" || key === "status" ? "wide-field" : ""}`;
  const labelElement = document.createElement("label"); labelElement.textContent = label; let control;
  if (Array.isArray(type)) { control = document.createElement("select"); for (const option of type) control.add(new Option(option, option, false, option === record[key])); }
  else if (type === "textarea") { control = document.createElement("textarea"); control.value = record[key] || ""; }
  else { control = document.createElement("input"); control.type = type || "text"; control.value = record[key] ?? ""; if (type === "number") { control.min = "1"; control.step = "1"; } }
  control.dataset.field = key; control.setAttribute("aria-label", label); wrapper.append(labelElement, control); return wrapper;
}

function renderRecords() {
  const container = $("#records"); container.innerHTML = "";
  for (const record of records) {
    const photo = photos.find(item => item.id === record.photoId); if (!photo) continue;
    const card = $("#record-template").content.firstElementChild.cloneNode(true); card.dataset.id = record.id;
    const image = new Image(); image.alt = `${photo.number}: ${photo.name}`; const url = imageUrl(photo); image.src = url; revokeImageUrl(image, url);
    card.querySelector(".record-photo").append(image); card.querySelector(".record-id").textContent = record.id;
    const sourceSelect = card.querySelector(".record-photo-select");
    for (const optionPhoto of photos) sourceSelect.add(new Option(`${optionPhoto.number} · ${optionPhoto.name}`, optionPhoto.id, false, optionPhoto.id === record.photoId));
    const fieldContainer = card.querySelector(".fields"); for (const field of fields) fieldContainer.append(createField(record, field)); container.append(card);
  }
  $("#empty-state").hidden = Boolean(records.length);
}

function render() {
  renderPhotos(); renderRecords();
  $("#photo-count").textContent = `${photos.length} photo${photos.length === 1 ? "" : "s"}`;
  $("#row-count").textContent = `${records.length} record${records.length === 1 ? "" : "s"}`;
  $("#create-inventory").disabled = !photos.length; $("#add-row").disabled = !photos.length; $("#export-xlsx").disabled = !records.length; $("#export-csv").disabled = !records.length;
}

function nextSequence(photoId) { const used = records.filter(record => record.photoId === photoId).map(record => Number(record.id.match(/-(\d+)$/)?.[1] || 0)); return Math.max(0, ...used) + 1; }
function addRecord(photo = photos[0]) { if (!photo) return; records.push(createRecord(photo, nextSequence(photo.id))); saveState(); render(); }
function createInventory() { for (const photo of photos) if (!records.some(record => record.photoId === photo.id)) addRecord(photo); showMessage("Inventory rows created. Unknown details remain marked for review."); globalThis.gtag?.("event", "inventory_created", {record_count: records.length}); }
function duplicateRecord(id) { const source = records.find(record => record.id === id); if (!source) return; const photo = photos.find(item => item.id === source.photoId); const copy = {...source, id: createRecord(photo, nextSequence(photo.id)).id}; records.push(copy); saveState(); render(); }
function download(name, type, data) { const url = URL.createObjectURL(new Blob([data], {type})); const link = document.createElement("a"); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
function exportExcel() { if (!globalThis.XLSX) return showMessage("Excel could not load. Saving as CSV remains available."); try { const rows = exportRows(records); const sheet = XLSX.utils.json_to_sheet(rows); sheet["!freeze"] = {xSplit: 0, ySplit: 1}; sheet["!cols"] = Object.keys(rows[0]).map(key => ({wch: Math.min(42, Math.max(12, key.length + 2))})); const workbook = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(workbook, sheet, "Inventory"); XLSX.writeFile(workbook, "AI-Stamp-Inventory-Beta-v1.xlsx"); globalThis.gtag?.("event", "inventory_export", {format: "xlsx", record_count: records.length}); } catch { showMessage("Saving as Excel failed. Your inventory is unchanged; save as CSV or try again."); } }

$("#photo-input").addEventListener("change", event => { addFiles(event.target.files); event.target.value = ""; });
$("#camera-input").addEventListener("change", event => { addFiles(event.target.files); event.target.value = ""; });
$("#create-inventory").onclick = createInventory;
$("#add-row").onclick = () => addRecord();
$("#export-xlsx").onclick = exportExcel;
$("#export-csv").onclick = () => { download("AI-Stamp-Inventory-Beta-v1.csv", "text/csv;charset=utf-8", toCsv(records)); globalThis.gtag?.("event", "inventory_export", {format: "csv", record_count: records.length}); };
$("#clear-all").onclick = async () => {
  if (!photos.length || confirm("Clear all photos and inventory records from this browser? Photo numbering will continue in this browser session.")) {
    photos = []; records = []; localStorage.removeItem(STORAGE_KEY); let recoveryCleared = true;
    try { await removeStoredPhotos(); } catch { recoveryCleared = false; }
    render(); const nextLabel = photoNumber(nextPhotoSequence - 1);
    showMessage(recoveryCleared ? `Inventory cleared. The next photo will be ${nextLabel}.` : `Inventory cleared from this session. The next photo will be ${nextLabel}, but browser recovery storage could not be cleared.`);
  }
};
$("#records").addEventListener("input", event => { const card = event.target.closest(".record-card"), record = records.find(item => item.id === card?.dataset.id), field = event.target.dataset.field; if (!record || !field) return; if (field === "photoId") { const photo = photos.find(item => item.id === event.target.value); if (!photo || photo.id === record.photoId) return; record.id = nextRecordId(photo, records); record.photoId = photo.id; record.photoNumber = photo.number; record.filename = photo.name; record.imageReference = `${photo.number} — ${photo.name}`; saveState(); render(); return; } record[field] = event.target.value; saveState(); });
$("#records").addEventListener("click", event => { const button = event.target.closest("button[data-action]"); if (!button) return; const id = button.closest(".record-card").dataset.id; if (button.dataset.action === "duplicate") duplicateRecord(id); else { records = records.filter(record => record.id !== id); saveState(); render(); } });

restoreState().then(render);
