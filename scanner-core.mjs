export const INVENTORY_FIELDS = [
  "Record ID", "Photo Number", "Original Filename", "Image Reference",
  "Country / Possible Country", "Approximate Period", "Denomination", "Currency",
  "Main Colour", "Subject / Design", "Used / Unused", "Quantity", "Confidence",
  "Further Research", "Collector Notes", "Information Status",
];

export function photoNumber(index) {
  return `Photo ${String(index + 1).padStart(3, "0")}`;
}

export function nextRecordId(photo, records) {
  const prefix = photo.number.replace("Photo ", "P");
  const used = records
    .filter(record => record.photoId === photo.id)
    .map(record => Number(record.id.match(/-(\d+)$/)?.[1] || 0));
  return `${prefix}-${String(Math.max(0, ...used) + 1).padStart(3, "0")}`;
}

export function partitionPhotoFiles(files, currentCount = 0, maximum = 20) {
  const acceptedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
  const available = Math.max(0, maximum - currentCount);
  const supported = [...files].filter(file => acceptedTypes.has(file.type));
  return {
    accepted: supported.slice(0, available),
    unsupported: [...files].filter(file => !acceptedTypes.has(file.type)),
    overLimit: Math.max(0, supported.length - available),
  };
}

export function createRecord(photo, sequence = 1) {
  const suffix = String(sequence).padStart(3, "0");
  return {
    id: `${photo.number.replace("Photo ", "P")}-${suffix}`,
    photoId: photo.id,
    photoNumber: photo.number,
    filename: photo.name,
    imageReference: `${photo.number} — ${photo.name}`,
    country: "Unknown",
    period: "Unknown",
    denomination: "",
    currency: "",
    colour: "",
    subject: "",
    usage: "Uncertain",
    quantity: 1,
    confidence: "Needs review",
    furtherResearch: "No",
    notes: "",
    status: "AI not connected — manual review",
  };
}

export function exportRows(records) {
  return records.map(record => ({
    "Record ID": record.id,
    "Photo Number": record.photoNumber,
    "Original Filename": record.filename,
    "Image Reference": record.imageReference,
    "Country / Possible Country": record.country,
    "Approximate Period": record.period,
    "Denomination": record.denomination,
    "Currency": record.currency,
    "Main Colour": record.colour,
    "Subject / Design": record.subject,
    "Used / Unused": record.usage,
    "Quantity": Number(record.quantity) || 1,
    "Confidence": record.confidence,
    "Further Research": record.furtherResearch,
    "Collector Notes": record.notes,
    "Information Status": record.status,
  }));
}

export function csvEscape(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

export function toCsv(records) {
  const rows = exportRows(records);
  return "\uFEFF" + [INVENTORY_FIELDS, ...rows.map(row => INVENTORY_FIELDS.map(field => row[field]))]
    .map(row => row.map(csvEscape).join(",")).join("\r\n");
}
