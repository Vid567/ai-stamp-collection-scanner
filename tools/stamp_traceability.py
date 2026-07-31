#!/usr/bin/env python3
"""Create traceable stamp crops, thumbnails and an image-enriched workbook.

This optional Phase 1 post-processor extends the existing prompt-to-Excel
workflow. It does not perform identification, OCR, detection or classification.
Bounding boxes come from the AI TSV output and are validated before use.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from PIL import Image, ImageOps


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
) -> None:
    """Generate lossless crops and non-upscaled centered PNG thumbnails."""

    crops_dir, thumbs_dir, photos_output = (
        output_dir / "Crops", output_dir / "Thumbnails", output_dir / "Photos"
    )
    for folder in (crops_dir, thumbs_dir, photos_output):
        folder.mkdir(parents=True, exist_ok=True)

    grouped: defaultdict[Path, list[Detection]] = defaultdict(list)
    for detection in detections:
        grouped[detection.source_path].append(detection)

    for source_path, photo_detections in grouped.items():
        shutil.copy2(source_path, photos_output / source_path.name)
        with Image.open(source_path) as raw:
            image = ImageOps.exif_transpose(raw)
            image.load()
            width, height = image.size
            for detection in photo_detections:
                detection.image_width, detection.image_height = width, height
                box = detection.bbox.pixels(width, height, margin)
                detection.crop_box = box
                crop = image.crop(box)
                crop.save(crops_dir / detection.crop_filename, format="PNG", optimize=True)

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
                canvas.save(thumbs_dir / detection.thumbnail_filename, format="PNG", optimize=True)


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


def build_workbook(template_path: Path, detections: list[Detection], output_dir: Path) -> Path:
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
    for header in [*LINK_HEADERS, *TRACE_HEADERS]:
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
            if header in {"year", "face_value", "quantity", "est_unit_value"} and value not in {"", None}:
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
    if not workbook_path.is_file():
        errors.append("Excel workbook is missing")
        image_count = 0
    else:
        with zipfile.ZipFile(workbook_path) as workbook_zip:
            image_count = len([name for name in workbook_zip.namelist() if name.startswith("xl/media/")])
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


def process(tsv_path: Path, photos_dir: Path, template_path: Path, output_dir: Path,
            margin: float = 0.04, thumbnail_size: int = 256) -> dict[str, object]:
    """Run the complete, deterministic Phase 1 post-processing pipeline."""

    output_dir.mkdir(parents=True, exist_ok=True)
    detections = read_detections(tsv_path, photos_dir)
    generate_images(detections, output_dir, margin, thumbnail_size)
    workbook_path = build_workbook(template_path, detections, output_dir)
    report = validate_output(detections, output_dir, workbook_path)
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
