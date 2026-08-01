#!/usr/bin/env python3
"""Create traceable stamp crops, thumbnails and an image-enriched workbook.

This optional Phase 1 post-processor extends the existing prompt-to-Excel
workflow. It does not perform identification, OCR, detection or classification.
Bounding boxes come from the AI TSV output and are validated before use.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import tempfile
import time
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from PIL import Image, ImageOps

from stamp_research import ResearchResult, analyse_crop, collection_summary, mark_duplicates


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAW_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)
ET.register_namespace("xdr", DRAW_NS)
ET.register_namespace("a", A_NS)

EXISTING_HEADERS = [
    "stamp_id", "photo", "position", "country_as_printed",
    "country_normalized", "year", "currency", "face_value", "value_unit",
    "stamp_type", "colour", "theme", "overprint", "on_piece", "condition",
    "needs_physical_check", "research_priority", "quantity", "est_unit_value",
    "line_value", "id_confidence", "notes",
]
LINK_HEADERS = [
    "record_id", "photo_number", "original_filename", "photo_references",
    "stamp_image_reference",
]
TRACE_HEADERS = [
    "thumbnail", "confidence_score", "bounding_box", "coordinates",
    "crop_filename", "thumbnail_filename",
]
RESEARCH_HEADERS = [
    "ai_country", "confidence_country", "ai_year", "confidence_year",
    "ai_theme", "confidence_theme", "ai_category", "confidence_category",
    "ai_series", "confidence_series", "ai_denomination",
    "confidence_denomination", "visible_text", "language", "ai_purpose",
    "visual_traits", "estimated_period", "dominant_colour",
    "image_quality_score", "image_quality", "quality_flags",
    "rescan_recommended", "research_recommendation", "duplicate_candidate",
    "duplicate_similarity", "overall_confidence", "research_notes",
    "identification_confidence", "period_confidence", "research_confidence",
    "country_reasoning", "interest_score", "interest_label", "research_priority",
    "possible_features", "interest_reasons", "research_checklist", "duplicate_group",
    "grouping", "collector_notes", "decision_path", "decision_source",
]
CONFIDENCE_HEADERS = {
    "confidence_country", "confidence_year", "confidence_theme",
    "confidence_category", "confidence_series", "confidence_denomination",
    "image_quality_score", "duplicate_similarity", "overall_confidence",
    "identification_confidence", "period_confidence", "research_confidence",
}
INPUT_COORDINATE_HEADERS = ["bbox_x", "bbox_y", "bbox_width", "bbox_height"]
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


class TraceabilityError(ValueError):
    """Raised when input cannot produce a trustworthy traceability chain."""


@dataclass(frozen=True)
class BoundingBox:
    """A normalized or pixel bounding box from the existing AI output."""

    x: float
    y: float
    width: float
    height: float
    normalized: bool = True

    def validate(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(math.isfinite(v) for v in values):
            raise TraceabilityError("Bounding box contains a non-finite value")
        if self.width <= 0 or self.height <= 0 or self.x < 0 or self.y < 0:
            raise TraceabilityError(f"Invalid bounding box: {values}")
        if self.normalized and (self.x + self.width > 1.0001 or self.y + self.height > 1.0001):
            raise TraceabilityError(f"Normalized bounding box exceeds image bounds: {values}")

    def pixels(self, image_width: int, image_height: int, margin: float) -> tuple[int, int, int, int]:
        self.validate()
        if self.normalized:
            x, y = self.x * image_width, self.y * image_height
            width, height = self.width * image_width, self.height * image_height
        else:
            x, y, width, height = self.x, self.y, self.width, self.height
        margin_x, margin_y = width * margin, height * margin
        left = max(0, math.floor(x - margin_x))
        top = max(0, math.floor(y - margin_y))
        right = min(image_width, math.ceil(x + width + margin_x))
        bottom = min(image_height, math.ceil(y + height + margin_y))
        if right <= left or bottom <= top:
            raise TraceabilityError("Bounding box produces an empty crop")
        return left, top, right, bottom


@dataclass
class Detection:
    """One stamp plus its permanent source and generated-file metadata."""

    row: dict[str, str]
    stamp_id: str
    record_id: str
    photo_filename: str
    photo_number: int
    detection_number: int
    bbox: BoundingBox
    source_path: Path
    crop_filename: str
    thumbnail_filename: str
    image_width: int = 0
    image_height: int = 0
    crop_box: tuple[int, int, int, int] | None = None
    research: ResearchResult | None = None


def _safe_float(value: str, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TraceabilityError(f"{field} must be numeric, got {value!r}") from exc


def read_detections(tsv_path: Path, photos_dir: Path) -> list[Detection]:
    """Parse AI TSV output and assign stable photo/detection numbers."""

    with tsv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        headers = reader.fieldnames or []
        required = {"stamp_id", "photo", *INPUT_COORDINATE_HEADERS}
        missing = sorted(required - set(headers))
        if missing:
            raise TraceabilityError(f"TSV is missing required columns: {', '.join(missing)}")
        rows = [dict(row) for row in reader]

    if not rows:
        raise TraceabilityError("TSV contains no stamp rows")

    photo_numbers: dict[str, int] = {}
    per_photo_count: defaultdict[str, int] = defaultdict(int)
    seen_ids: set[str] = set()
    seen_record_ids: set[str] = set()
    detections: list[Detection] = []

    for row_index, row in enumerate(rows, start=2):
        stamp_id = (row.get("stamp_id") or "").strip()
        photo = Path((row.get("photo") or "").strip()).name
        if not stamp_id:
            raise TraceabilityError(f"Row {row_index}: stamp_id is blank")
        if stamp_id in seen_ids:
            raise TraceabilityError(f"Row {row_index}: duplicate stamp_id {stamp_id!r}")
        if not photo:
            raise TraceabilityError(f"Row {row_index}: photo is blank")
        source = photos_dir / photo
        if not source.is_file():
            raise TraceabilityError(f"Row {row_index}: source photograph does not exist: {source}")
        if source.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise TraceabilityError(f"Row {row_index}: unsupported image type: {source.suffix}")

        photo_numbers.setdefault(photo, len(photo_numbers) + 1)
        assigned_photo_number = photo_numbers[photo]
        supplied_photo_number = (row.get("photo_number") or "").strip()
        if supplied_photo_number:
            digits = "".join(character for character in supplied_photo_number if character.isdigit())
            if not digits or int(digits) != assigned_photo_number:
                raise TraceabilityError(
                    f"Row {row_index}: photo_number {supplied_photo_number!r} does not match upload order "
                    f"Photo {assigned_photo_number:03d}"
                )
        per_photo_count[photo] += 1
        normalized_value = (row.get("bbox_normalized") or "yes").strip().lower()
        bbox = BoundingBox(
            _safe_float(row["bbox_x"], "bbox_x"),
            _safe_float(row["bbox_y"], "bbox_y"),
            _safe_float(row["bbox_width"], "bbox_width"),
            _safe_float(row["bbox_height"], "bbox_height"),
            normalized=normalized_value not in {"no", "false", "0", "pixels"},
        )
        bbox.validate()
        seen_ids.add(stamp_id)
        record_id = (row.get("record_id") or stamp_id).strip()
        if record_id in seen_record_ids:
            raise TraceabilityError(f"Row {row_index}: duplicate record_id {record_id!r}")
        seen_record_ids.add(record_id)
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in record_id)
        detections.append(Detection(
            row=row,
            stamp_id=stamp_id,
            record_id=record_id,
            photo_filename=photo,
            photo_number=assigned_photo_number,
            detection_number=per_photo_count[photo],
            bbox=bbox,
            source_path=source,
            crop_filename=f"{safe_id}.png",
            thumbnail_filename=f"{safe_id}_thumb.png",
        ))
    return detections


def generate_images(
    detections: Iterable[Detection], output_dir: Path, margin: float = 0.04,
    thumbnail_size: int = 256,
) -> int:
    """Generate images once and reuse unchanged crop/thumbnail results."""

    crops_dir, thumbs_dir, photos_output = (
        output_dir / "Crops", output_dir / "Thumbnails", output_dir / "Photos"
    )
    for folder in (crops_dir, thumbs_dir, photos_output):
        folder.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "processing-cache.json"
    try:
        old_cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        old_cache = {}
    new_cache: dict[str, str] = {}
    cache_hits = 0

    grouped: defaultdict[Path, list[Detection]] = defaultdict(list)
    for detection in detections:
        grouped[detection.source_path].append(detection)

    for source_path, photo_detections in grouped.items():
        shutil.copy2(source_path, photos_output / source_path.name)
        source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        with Image.open(source_path) as raw:
            image = ImageOps.exif_transpose(raw)
            image.load()
            width, height = image.size
            for detection in photo_detections:
                detection.image_width, detection.image_height = width, height
                box = detection.bbox.pixels(width, height, margin)
                detection.crop_box = box
                fingerprint = hashlib.sha256(json.dumps({
                    "source": source_digest, "box": box, "thumbnail_size": thumbnail_size,
                }, sort_keys=True).encode()).hexdigest()
                new_cache[detection.record_id] = fingerprint
                crop_path = crops_dir / detection.crop_filename
                thumb_path = thumbs_dir / detection.thumbnail_filename
                if old_cache.get(detection.record_id) == fingerprint and crop_path.is_file() and thumb_path.is_file():
                    cache_hits += 1
                    continue
                crop = image.crop(box)
                crop.save(crop_path, format="PNG", optimize=True)

                thumb = crop.copy()
                thumb.thumbnail((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)
                background_mode = "RGBA" if "A" in thumb.getbands() else "RGB"
                background_color = (255, 255, 255, 0) if background_mode == "RGBA" else (255, 255, 255)
                canvas = Image.new(background_mode, (thumbnail_size, thumbnail_size), background_color)
                offset = ((thumbnail_size - thumb.width) // 2, (thumbnail_size - thumb.height) // 2)
                if background_mode == "RGBA" and thumb.mode == "RGBA":
                    canvas.paste(thumb, offset, thumb)
                else:
                    canvas.paste(thumb.convert(background_mode), offset)
                canvas.save(thumb_path, format="PNG", optimize=True)
    cache_path.write_text(json.dumps(new_cache, indent=2), encoding="utf-8")
    return cache_hits


def enrich_research(detections: list[Detection], output_dir: Path) -> list[ResearchResult]:
    """Attach conservative Phase 2/3 research and write an auditable decision log."""
    results: list[ResearchResult] = []
    for detection in detections:
        if detection.crop_box is None:
            raise TraceabilityError(f"{detection.record_id}: crop box was not generated")
        left, top, right, bottom = detection.crop_box
        touches_edge = left == 0 or top == 0 or right == detection.image_width or bottom == detection.image_height
        result = analyse_crop(
            detection.record_id,
            detection.row,
            output_dir / "Crops" / detection.crop_filename,
            touches_edge,
        )
        detection.research = result
        results.append(result)
    mark_duplicates(results)
    cache = {result.record_id: result.excel_values() for result in results}
    (output_dir / "research-results.json").write_text(json.dumps(cache, indent=2), encoding="utf-8")
    decisions = [
        {"record_id": result.record_id, "reason": result.interest_reasons,
         "confidence": result.research_confidence, "decision_path": result.decision_path,
         "source": result.decision_source}
        for result in results
    ]
    (output_dir / "ai-decision-log.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in decisions), encoding="utf-8"
    )
    return results


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _inline_cell(reference: str, value: str, style: str | None = None) -> ET.Element:
    attrs = {"r": reference, "t": "inlineStr"}
    if style is not None:
        attrs["s"] = style
    cell = ET.Element(f"{{{MAIN_NS}}}c", attrs)
    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    text = ET.SubElement(inline, f"{{{MAIN_NS}}}t")
    text.text = value
    return cell


def _number_cell(reference: str, value: int | float, style: str | None = None) -> ET.Element:
    attrs = {"r": reference}
    if style is not None:
        attrs["s"] = style
    cell = ET.Element(f"{{{MAIN_NS}}}c", attrs)
    ET.SubElement(cell, f"{{{MAIN_NS}}}v").text = str(value)
    return cell


def _workbook_sheet_path(entries: dict[str, bytes], sheet_name: str) -> str:
    workbook = ET.fromstring(entries["xl/workbook.xml"])
    relationships = ET.fromstring(entries["xl/_rels/workbook.xml.rels"])
    targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships}
    sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
    if sheets is None:
        raise TraceabilityError("Workbook has no sheets collection")
    for sheet in sheets:
        if sheet.attrib.get("name") == sheet_name:
            rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
            target = targets[rel_id].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise TraceabilityError(f"Workbook does not contain sheet {sheet_name!r}")


def _write_collection_summary(entries: dict[str, bytes], summary: dict[str, object]) -> None:
    """Populate or add the collection-insights worksheet."""
    existing_summary = True
    try:
        sheet_path = _workbook_sheet_path(entries, "Collection Summary")
    except TraceabilityError:
        existing_summary = False
        workbook = ET.fromstring(entries["xl/workbook.xml"])
        relationships = ET.fromstring(entries["xl/_rels/workbook.xml.rels"])
        sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
        if sheets is None:
            raise TraceabilityError("Workbook has no sheets collection")
        next_sheet_id = max(int(sheet.attrib.get("sheetId", "0")) for sheet in sheets) + 1
        existing_paths = [name for name in entries if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
        next_file_id = max(int(Path(path).stem.removeprefix("sheet")) for path in existing_paths) + 1
        rel_id = "rIdPhase2Summary"
        ET.SubElement(sheets, f"{{{MAIN_NS}}}sheet", {
            "name": "Collection Summary", "sheetId": str(next_sheet_id), f"{{{REL_NS}}}id": rel_id,
        })
        ET.SubElement(relationships, f"{{{PKG_REL_NS}}}Relationship", {
            "Id": rel_id,
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
            "Target": f"worksheets/sheet{next_file_id}.xml",
        })
        entries["xl/workbook.xml"] = ET.tostring(workbook, encoding="utf-8", xml_declaration=True)
        entries["xl/_rels/workbook.xml.rels"] = ET.tostring(relationships, encoding="utf-8", xml_declaration=True)
        sheet_path = f"xl/worksheets/sheet{next_file_id}.xml"
        content_types = entries["[Content_Types].xml"].decode("utf-8")
        override = (
            f'<Override PartName="/{sheet_path}" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        entries["[Content_Types].xml"] = content_types.replace("</Types>", override + "</Types>").encode()

    if existing_summary:
        worksheet = ET.fromstring(entries[sheet_path])
        data = worksheet.find(f"{{{MAIN_NS}}}sheetData")
        if data is None:
            data = ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetData")
        styles = {
            cell.attrib.get("r", ""): cell.attrib.get("s")
            for cell in data.iter(f"{{{MAIN_NS}}}c")
        }
        for row in list(data):
            data.remove(row)
    else:
        worksheet = ET.Element(f"{{{MAIN_NS}}}worksheet")
        ET.SubElement(worksheet, f"{{{MAIN_NS}}}dimension", {"ref": "A1:B16"})
        views = ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetViews")
        ET.SubElement(views, f"{{{MAIN_NS}}}sheetView", {"workbookViewId": "0", "showGridLines": "0"})
        cols = ET.SubElement(worksheet, f"{{{MAIN_NS}}}cols")
        ET.SubElement(cols, f"{{{MAIN_NS}}}col", {"min": "1", "max": "1", "width": "30", "customWidth": "1"})
        ET.SubElement(cols, f"{{{MAIN_NS}}}col", {"min": "2", "max": "2", "width": "45", "customWidth": "1"})
        data = ET.SubElement(worksheet, f"{{{MAIN_NS}}}sheetData")
        styles = {}
    title_row = ET.SubElement(data, f"{{{MAIN_NS}}}row", {"r": "1", "ht": "28", "customHeight": "1"})
    title_row.append(_inline_cell("A1", "Collection Summary", styles.get("A1")))
    title_row.append(_inline_cell("B1", "AI-assisted findings; verify important identifications", styles.get("B1")))
    labels = [
        ("Uploaded photographs", "uploaded_photographs"), ("Detected stamps", "detected_stamps"),
        ("Average confidence", "average_confidence"), ("Countries detected", "countries_detected"),
        ("Top countries", "top_countries"), ("Themes detected", "themes_detected"),
        ("Top themes", "top_themes"), ("Duplicate candidates", "duplicate_candidates"),
        ("Unknown stamps", "unknown_stamps"), ("Low-quality images", "low_quality_images"),
        ("Manual review count", "manual_review_count"), ("Research candidates", "research_candidates"),
        ("Average image quality", "average_image_quality"),
        ("Top recommendations", "top_recommendations"), ("Processing time (seconds)", "processing_seconds"),
        ("Estimated periods", "estimated_periods"), ("Interest levels", "interest_levels"),
        ("High-interest candidates", "high_interest_candidates"),
        ("Exceptional research candidates", "exceptional_research_candidates"),
        ("Duplicate groups", "duplicate_groups"),
    ]
    numeric = {"uploaded_photographs", "detected_stamps", "average_confidence", "countries_detected", "themes_detected", "duplicate_candidates", "unknown_stamps", "low_quality_images", "manual_review_count", "research_candidates", "average_image_quality", "processing_seconds", "high_interest_candidates", "exceptional_research_candidates", "duplicate_groups"}
    for row_number, (label, key) in enumerate(labels, start=2):
        row = ET.SubElement(data, f"{{{MAIN_NS}}}row", {"r": str(row_number)})
        row.append(_inline_cell(f"A{row_number}", label, styles.get(f"A{row_number}")))
        value = summary.get(key, "")
        if key in numeric:
            row.append(_number_cell(f"B{row_number}", float(value or 0), styles.get(f"B{row_number}")))
        else:
            display = ", ".join(f"{name} ({count})" for name, count in value) if isinstance(value, list) else str(value)
            row.append(_inline_cell(f"B{row_number}", display, styles.get(f"B{row_number}")))
    entries[sheet_path] = ET.tostring(worksheet, encoding="utf-8", xml_declaration=True)


def build_workbook(template_path: Path, detections: list[Detection], output_dir: Path,
                   summary: dict[str, object]) -> Path:
    """Populate either the v2.0 or photo-linked v2.1 workbook and embed thumbnails."""

    output_path = output_dir / "Stamp Inventory.xlsx"
    with zipfile.ZipFile(template_path, "r") as source_zip:
        entries = {name: source_zip.read(name) for name in source_zip.namelist()}

    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in entries:
        shared_root = ET.fromstring(entries["xl/sharedStrings.xml"])
        shared_strings = [
            "".join(text.text or "" for text in item.iter(f"{{{MAIN_NS}}}t"))
            for item in shared_root
        ]

    sheet_path = _workbook_sheet_path(entries, "Inventory")
    sheet = ET.fromstring(entries[sheet_path])
    sheet_data = sheet.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is None:
        raise TraceabilityError("Inventory sheet has no sheetData")
    rows = {int(row.attrib["r"]): row for row in sheet_data.findall(f"{{{MAIN_NS}}}row")}
    header_row = rows[1]

    def cell_text(cell: ET.Element) -> str:
        cell_type = cell.attrib.get("t")
        value = cell.find(f"{{{MAIN_NS}}}v")
        if cell_type == "s" and value is not None:
            return shared_strings[int(value.text or 0)]
        if cell_type == "inlineStr":
            return "".join(text.text or "" for text in cell.iter(f"{{{MAIN_NS}}}t"))
        return value.text if value is not None and value.text else ""

    header_map: dict[str, int] = {}
    for cell in header_row.findall(f"{{{MAIN_NS}}}c"):
        reference = cell.attrib.get("r", "")
        letters = "".join(character for character in reference if character.isalpha())
        index = 0
        for character in letters:
            index = index * 26 + ord(character.upper()) - 64
        header_map[cell_text(cell)] = index

    old_header_cells = header_row.findall(f"{{{MAIN_NS}}}c")
    header_style = old_header_cells[-1].attrib.get("s") if old_header_cells else None
    next_column = max(header_map.values()) + 1
    for header in [*LINK_HEADERS, *TRACE_HEADERS, *RESEARCH_HEADERS]:
        if header not in header_map:
            header_map[header] = next_column
            header_row.append(_inline_cell(f"{_column_name(next_column)}1", header, header_style))
            next_column += 1

    line_value_column = header_map["line_value"]
    thumbnail_column = header_map["thumbnail"]
    photo_label = lambda detection: f"Photo {detection.photo_number:03d}"

    for excel_row, detection in enumerate(detections, start=2):
        if excel_row > 201:
            raise TraceabilityError("Current workbook supports at most 200 Inventory rows")
        row_element = rows.get(excel_row)
        if row_element is None:
            row_element = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(excel_row)})
            rows[excel_row] = row_element
        row_element.attrib.update({"ht": "198", "customHeight": "1"})

        row_values = {header: detection.row.get(header, "") for header in EXISTING_HEADERS}
        row_values.update({
            "stamp_id": detection.stamp_id,
            "photo": detection.photo_filename,
            "record_id": detection.record_id,
            "photo_number": photo_label(detection),
            "original_filename": detection.photo_filename,
            "photo_references": detection.row.get("photo_references") or photo_label(detection),
            "stamp_image_reference": detection.crop_filename,
            "thumbnail": "",
            "confidence_score": detection.row.get("confidence_score", ""),
            "bounding_box": json.dumps({
                "x": detection.bbox.x, "y": detection.bbox.y,
                "width": detection.bbox.width, "height": detection.bbox.height,
                "normalized": detection.bbox.normalized,
            }, separators=(",", ":")),
            "coordinates": json.dumps({
                "center_x": detection.bbox.x + detection.bbox.width / 2,
                "center_y": detection.bbox.y + detection.bbox.height / 2,
                "image_width": detection.image_width, "image_height": detection.image_height,
            }, separators=(",", ":")),
            "crop_filename": detection.crop_filename,
            "thumbnail_filename": detection.thumbnail_filename,
        })
        if detection.research is not None:
            row_values.update(detection.research.excel_values())
        for child in list(row_element):
            reference = child.attrib.get("r", "")
            letters = "".join(character for character in reference if character.isalpha())
            if letters != _column_name(line_value_column):
                row_element.remove(child)
        for header, column_index in sorted(header_map.items(), key=lambda item: item[1]):
            if column_index == line_value_column:
                continue
            value = row_values.get(header, detection.row.get(header, ""))
            reference = f"{_column_name(column_index)}{excel_row}"
            if header in {"year", "face_value", "quantity", "est_unit_value", *CONFIDENCE_HEADERS} and value not in {"", None}:
                try:
                    row_element.append(_number_cell(reference, float(value)))
                    continue
                except (TypeError, ValueError):
                    pass
            row_element.append(_inline_cell(reference, str(value or "")))

    max_column = max(header_map.values())
    dimension = sheet.find(f"{{{MAIN_NS}}}dimension")
    if dimension is not None:
        dimension.attrib["ref"] = f"A1:{_column_name(max_column)}208"
    cols = sheet.find(f"{{{MAIN_NS}}}cols")
    if cols is None:
        cols = ET.Element(f"{{{MAIN_NS}}}cols")
        sheet.insert(1, cols)
    widths = {
        "thumbnail": 38, "record_id": 14, "photo_number": 13,
        "original_filename": 24, "photo_references": 22,
        "stamp_image_reference": 24, "confidence_score": 14,
        "bounding_box": 28, "coordinates": 28, "crop_filename": 24,
        "thumbnail_filename": 28,
        "ai_country": 20, "ai_year": 12, "ai_theme": 20,
        "ai_category": 18, "ai_series": 24, "ai_denomination": 18,
        "visible_text": 28, "language": 14, "ai_purpose": 18,
        "visual_traits": 28, "estimated_period": 18, "dominant_colour": 18,
        "image_quality": 16, "quality_flags": 30, "rescan_recommended": 18,
        "research_recommendation": 28, "duplicate_candidate": 28,
        "research_notes": 34,
        "country_reasoning": 36, "interest_label": 30, "research_priority": 18,
        "possible_features": 34, "interest_reasons": 42, "research_checklist": 52,
        "duplicate_group": 16, "grouping": 14, "collector_notes": 34,
        "decision_path": 45, "decision_source": 34,
    }
    for header, width in widths.items():
        column_index = header_map[header]
        ET.SubElement(cols, f"{{{MAIN_NS}}}col", {
            "min": str(column_index), "max": str(column_index),
            "width": str(width), "customWidth": "1",
        })

    drawing_rel_id = "rIdPhase1Drawing"
    drawing = sheet.find(f"{{{MAIN_NS}}}drawing")
    if drawing is None:
        drawing = ET.SubElement(sheet, f"{{{MAIN_NS}}}drawing", {f"{{{REL_NS}}}id": drawing_rel_id})
    else:
        drawing.attrib[f"{{{REL_NS}}}id"] = drawing_rel_id
    entries[sheet_path] = ET.tostring(sheet, encoding="utf-8", xml_declaration=True)

    sheet_rels_path = str(Path(sheet_path).parent / "_rels" / f"{Path(sheet_path).name}.rels")
    sheet_rels = ET.fromstring(entries[sheet_rels_path]) if sheet_rels_path in entries else ET.Element("Relationships", xmlns=PKG_REL_NS)
    for relationship in list(sheet_rels):
        if relationship.attrib.get("Id") == drawing_rel_id:
            sheet_rels.remove(relationship)
    ET.SubElement(sheet_rels, "Relationship", {
        "Id": drawing_rel_id,
        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing",
        "Target": "../drawings/drawing1.xml",
    })
    entries[sheet_rels_path] = ET.tostring(sheet_rels, encoding="utf-8", xml_declaration=True)

    drawing_root = ET.Element(f"{{{DRAW_NS}}}wsDr")
    drawing_rels = ET.Element("Relationships", xmlns=PKG_REL_NS)
    for index, detection in enumerate(detections, start=1):
        anchor = ET.SubElement(drawing_root, f"{{{DRAW_NS}}}oneCellAnchor")
        start = ET.SubElement(anchor, f"{{{DRAW_NS}}}from")
        for tag, value in (("col", thumbnail_column - 1), ("colOff", 45720), ("row", index), ("rowOff", 45720)):
            ET.SubElement(start, f"{{{DRAW_NS}}}{tag}").text = str(value)
        ET.SubElement(anchor, f"{{{DRAW_NS}}}ext", {"cx": "2438400", "cy": "2438400"})
        picture = ET.SubElement(anchor, f"{{{DRAW_NS}}}pic")
        nv = ET.SubElement(picture, f"{{{DRAW_NS}}}nvPicPr")
        ET.SubElement(nv, f"{{{DRAW_NS}}}cNvPr", {"id": str(index), "name": detection.thumbnail_filename})
        ET.SubElement(nv, f"{{{DRAW_NS}}}cNvPicPr")
        fill = ET.SubElement(picture, f"{{{DRAW_NS}}}blipFill")
        ET.SubElement(fill, f"{{{A_NS}}}blip", {f"{{{REL_NS}}}embed": f"rId{index}"})
        stretch = ET.SubElement(fill, f"{{{A_NS}}}stretch")
        ET.SubElement(stretch, f"{{{A_NS}}}fillRect")
        shape = ET.SubElement(picture, f"{{{DRAW_NS}}}spPr")
        transform = ET.SubElement(shape, f"{{{A_NS}}}xfrm")
        ET.SubElement(transform, f"{{{A_NS}}}off", {"x": "0", "y": "0"})
        ET.SubElement(transform, f"{{{A_NS}}}ext", {"cx": "2438400", "cy": "2438400"})
        geometry = ET.SubElement(shape, f"{{{A_NS}}}prstGeom", {"prst": "rect"})
        ET.SubElement(geometry, f"{{{A_NS}}}avLst")
        ET.SubElement(anchor, f"{{{DRAW_NS}}}clientData")
        ET.SubElement(drawing_rels, "Relationship", {
            "Id": f"rId{index}",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
            "Target": f"../media/image{index}.png",
        })
        entries[f"xl/media/image{index}.png"] = (output_dir / "Thumbnails" / detection.thumbnail_filename).read_bytes()
    entries["xl/drawings/drawing1.xml"] = ET.tostring(drawing_root, encoding="utf-8", xml_declaration=True)
    entries["xl/drawings/_rels/drawing1.xml.rels"] = ET.tostring(drawing_rels, encoding="utf-8", xml_declaration=True)

    content_types = entries["[Content_Types].xml"].decode("utf-8")
    additions = []
    if 'Extension="png"' not in content_types:
        additions.append('<Default Extension="png" ContentType="image/png"/>')
    if "/xl/drawings/drawing1.xml" not in content_types:
        additions.append(
            '<Override PartName="/xl/drawings/drawing1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
        )
    if additions:
        content_types = content_types.replace("</Types>", "".join(additions) + "</Types>")
    entries["[Content_Types].xml"] = content_types.encode("utf-8")

    _write_collection_summary(entries, summary)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as output_zip:
        for name, data in entries.items():
            output_zip.writestr(name, data)
    return output_path


def validate_output(detections: list[Detection], output_dir: Path, workbook_path: Path) -> dict[str, object]:
    """Validate all requested one-to-one relationships and file references."""

    errors: list[str] = []
    stamp_ids = [d.stamp_id for d in detections]
    record_ids = [d.record_id for d in detections]
    if len(stamp_ids) != len(set(stamp_ids)):
        errors.append("Stamp IDs are not unique")
    if len(record_ids) != len(set(record_ids)):
        errors.append("Record IDs are not unique")
    for detection in detections:
        expected = {
            "source photograph": output_dir / "Photos" / detection.photo_filename,
            "crop": output_dir / "Crops" / detection.crop_filename,
            "thumbnail": output_dir / "Thumbnails" / detection.thumbnail_filename,
        }
        for label, path in expected.items():
            if not path.is_file():
                errors.append(f"{detection.stamp_id}: {label} missing: {path}")
        if detection.research is None:
            errors.append(f"{detection.stamp_id}: Phase 2 research result missing")
        elif not 0 <= detection.research.overall_confidence <= 1:
            errors.append(f"{detection.stamp_id}: overall confidence is outside 0..1")
        elif not 0 <= detection.research.interest_score <= 100:
            errors.append(f"{detection.stamp_id}: interest score is outside 0..100")
    if not workbook_path.is_file():
        errors.append("Excel workbook is missing")
        image_count = 0
    else:
        with zipfile.ZipFile(workbook_path) as workbook_zip:
            image_count = len([name for name in workbook_zip.namelist() if name.startswith("xl/media/")])
            workbook_xml = workbook_zip.read("xl/workbook.xml").decode("utf-8")
            if "Collection Summary" not in workbook_xml:
                errors.append("Workbook is missing the Collection Summary worksheet")
        if image_count != len(detections):
            errors.append(f"Workbook contains {image_count} images for {len(detections)} stamps")
    report = {
        "status": "PASS" if not errors else "FAIL",
        "detected_stamps": len(detections),
        "excel_rows": len(detections),
        "embedded_thumbnails": image_count,
        "unique_stamp_ids": len(set(stamp_ids)),
        "unique_record_ids": len(set(record_ids)),
        "source_photos": len({d.photo_filename for d in detections}),
        "errors": errors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "validation-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def write_research_dashboard(results: list[ResearchResult], summary: dict[str, object], output_dir: Path) -> None:
    """Write a portable, read-only Research UI; all data remains local."""
    data = json.dumps([result.excel_values() for result in results], ensure_ascii=False).replace("</", "<\\/")
    summary_json = json.dumps(summary, ensure_ascii=False).replace("</", "<\\/")
    html = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Stamp Research</title><style>
body{font:15px system-ui;margin:0;background:#f5f7fa;color:#172033}header,main{max-width:1200px;margin:auto;padding:20px}.tabs,.filters{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}button,select{padding:10px;border:1px solid #ccd5e0;border-radius:9px;background:white}.active{background:#14365e;color:white}.stats,.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.stat,.card{background:white;border:1px solid #dce3eb;border-radius:14px;padding:16px}.score{font-size:28px;font-weight:800}.muted{color:#617086}.tag{display:inline-block;background:#e7eef7;padding:4px 8px;border-radius:99px;margin:2px}ul{padding-left:20px}.hidden{display:none}</style></head><body><header><h1>Research</h1><p class='muted'>AI-assisted research priorities. Scores are not rarity or value estimates.</p><div class='tabs'><button class='active'>Research</button><button onclick='showStats()'>Collection statistics</button></div><div class='filters'><select id='mode'><option value='interest'>Highest Interest</option><option value='confidence'>Highest Confidence</option><option value='unknown'>Unknown</option><option value='research'>Needs Research</option><option value='duplicates'>Duplicates</option></select><select id='country'><option value=''>All countries</option></select><select id='period'><option value=''>All periods</option></select></div></header><main><section id='stats' class='stats hidden'></section><section id='cards' class='cards'></section></main><script>
const rows=__DATA__,summary=__SUMMARY__;const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const country=document.querySelector('#country'),period=document.querySelector('#period');for(const [el,key] of [[country,'ai_country'],[period,'estimated_period']]){[...new Set(rows.map(r=>r[key]).filter(Boolean))].sort().forEach(v=>el.insertAdjacentHTML('beforeend',`<option>${esc(v)}</option>`))}
function render(){document.querySelector('#stats').classList.add('hidden');let list=[...rows],m=document.querySelector('#mode').value;if(m==='unknown')list=list.filter(r=>!r.ai_country);if(m==='research')list=list.filter(r=>r.interest_score>=25);if(m==='duplicates')list=list.filter(r=>r.duplicate_group);if(country.value)list=list.filter(r=>r.ai_country===country.value);if(period.value)list=list.filter(r=>r.estimated_period===period.value);list.sort((a,b)=>m==='confidence'?b.overall_confidence-a.overall_confidence:b.interest_score-a.interest_score);document.querySelector('#cards').innerHTML=list.map(r=>`<article class='card'><div class='score'>${r.interest_score}/100</div><strong>${esc(r.interest_label)}</strong><p>${esc(r.record_id)} · ${esc(r.ai_country||'Unknown')} · ${esc(r.estimated_period||r.ai_year||'Unknown period')}</p><span class='tag'>ID ${Math.round(r.identification_confidence*100)}%</span><span class='tag'>Country ${Math.round((r.confidence_country||0)*100)}%</span><span class='tag'>Period ${Math.round(r.period_confidence*100)}%</span><span class='tag'>Research ${Math.round(r.research_confidence*100)}%</span><h3>Why</h3><p>${esc(r.interest_reasons)}</p><h3>Checklist</h3><p>${esc(r.research_checklist)}</p><p class='muted'>${esc(r.duplicate_group||'')} ${esc(r.grouping)}</p></article>`).join('')||'<p>No matching stamps.</p>'}
function showStats(){document.querySelector('#cards').innerHTML='';let s=document.querySelector('#stats');s.classList.remove('hidden');s.innerHTML=Object.entries(summary).filter(([,v])=>!Array.isArray(v)).map(([k,v])=>`<div class='stat'><strong>${esc(k.replaceAll('_',' '))}</strong><div class='score'>${esc(v)}</div></div>`).join('')}document.querySelectorAll('select').forEach(e=>e.onchange=render);render();
</script></body></html>""".replace("__DATA__", data).replace("__SUMMARY__", summary_json)
    (output_dir / "research-dashboard.html").write_text(html, encoding="utf-8")


def process(tsv_path: Path, photos_dir: Path, template_path: Path, output_dir: Path,
            margin: float = 0.04, thumbnail_size: int = 256) -> dict[str, object]:
    """Run the backward-compatible Phase 1 pipeline plus Phase 2/3 enrichment."""

    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    detections = read_detections(tsv_path, photos_dir)
    cache_hits = generate_images(detections, output_dir, margin, thumbnail_size)
    research = enrich_research(detections, output_dir)
    summary = collection_summary(research, len({item.photo_filename for item in detections}), time.perf_counter() - started)
    (output_dir / "collection-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_research_dashboard(research, summary, output_dir)
    workbook_path = build_workbook(template_path, detections, output_dir, summary)
    report = validate_output(detections, output_dir, workbook_path)
    report["research_results"] = len(research)
    report["collection_summary"] = summary
    report["cache_hits"] = cache_hits
    (output_dir / "validation-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report["status"] != "PASS":
        raise TraceabilityError("Output validation failed; see validation-report.json")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detections", required=True, type=Path, help="Tab-separated AI output")
    parser.add_argument("--photos", required=True, type=Path, help="Folder containing original photographs")
    parser.add_argument("--template", required=True, type=Path, help="Existing Stamp Inventory .xlsx template")
    parser.add_argument("--output", required=True, type=Path, help="Output folder")
    parser.add_argument("--margin", type=float, default=0.04, help="Safety margin around each box (default: 0.04)")
    parser.add_argument("--thumbnail-size", type=int, default=256, help="Square thumbnail canvas in pixels")
    args = parser.parse_args(argv)
    if not 0 <= args.margin <= 0.5:
        parser.error("--margin must be between 0 and 0.5")
    try:
        report = process(args.detections, args.photos, args.template, args.output, args.margin, args.thumbnail_size)
    except (TraceabilityError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
