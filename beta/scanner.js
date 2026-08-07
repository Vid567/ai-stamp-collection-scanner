import { createRecord, exportRows, nextRecordId, partitionPhotoFiles, photoNumber, toCsv } from "./scanner-core.mjs";

const MAX_FILES = 20;
const STORAGE_KEY = "stampScannerBetaV1";
const PHOTO_SEQUENCE_KEY = "stampScannerBetaPhotoSequence";
const dbPromise = openDatabase();
let photos = [];
let records = [];
let nextPhotoSequence = Number.parseInt(sessionStorage.getItem(PHOTO_SEQUENCE_KEY) || "1", 10);
if (!Number.isFinite(nextPhotoSequence) || nextPhotoSequence < 1)