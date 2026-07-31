import csv
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "stamp_traceability.py"
TEMPLATE = ROOT / "test-fixtures" / "Stamp-Inventory-Template.xlsx"

HEADERS = [
    "stamp_id", "photo", "position", "country_as_printed", "country_normalized",
    "year", "currency", "face_value", "value_unit", "stamp_type", "colour",
    "theme", "overprint", "on_piece", "condition", "needs_physical_check",
    "research_priority", "quantity", "est_unit_value", "line_value",
    "id_confidence", "notes", "record_id", "photo_number", "original_filename",
    "photo_references", "stamp_image_reference", "bbox_x", "bbox_y", "bbox_width", "bbox_height",
    "bbox_normalized", "confidence_score",
    "ai_country", "confidence_country", "ai_year", "confidence_year",
    "ai_theme", "confidence_theme", "ai_category", "confidence_category",
    "ai_series", "confidence_series", "ai_denomination", "confidence_denomination",
    "visible_text", "language", "ai_purpose", "visual_traits", "estimated_period",
    "dominant_colour", "rare_characteristics", "research_recommendation",
]


class TraceabilityIntegrationTests(unittest.TestCase):
    def make_photo(self, path: Path, size: tuple[int, int], boxes: list[tuple[int, int, int, int]]) -> None:
        image = Image.new("RGB", size, "#EEE8D5")
        draw = ImageDraw.Draw(image)
        for index, box in enumerate(boxes):
            draw.rectangle(box, fill=(40 + index * 20, 90, 150), outline="black", width=3)
        image.save(path, quality=95)

    def write_tsv(self, path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    def base_row(self, stamp_id: str, photo: str, x: float, y: float, w: float, h: float) -> dict[str, str]:
        row = {header: "" for header in HEADERS}
        row.update({
            "stamp_id": stamp_id, "photo": photo, "position": "test position",
            "record_id": stamp_id, "original_filename": photo,
            "country_as_printed": "TEST", "country_normalized": "Testland",
            "stamp_type": "commemorative", "quantity": "1", "id_confidence": "medium",
            "ai_country": "Testland", "confidence_country": "82%",
            "ai_theme": "Test design", "confidence_theme": "0.9",
            "ai_category": "Commemorative", "confidence_category": "0.8",
            "bbox_x": str(x), "bbox_y": str(y), "bbox_width": str(w),
            "bbox_height": str(h), "bbox_normalized": "yes", "confidence_score": "0.8",
        })
        return row

    def run_tool(self, rows: list[dict[str, str]], photos: dict[str, tuple[tuple[int, int], list[tuple[int, int, int, int]]]]):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        photos_dir, output_dir = root / "Photos", root / "Output"
        photos_dir.mkdir()
        for filename, (size, boxes) in photos.items():
            self.make_photo(photos_dir / filename, size, boxes)
        tsv = root / "detections.tsv"
        self.write_tsv(tsv, rows)
        result = subprocess.run([
            sys.executable, str(TOOL), "--detections", str(tsv), "--photos", str(photos_dir),
            "--template", str(TEMPLATE), "--output", str(output_dir),
        ], text=True, capture_output=True)
        return temp, output_dir, result

    def test_single_photo_multiple_stamps(self):
        rows = [
            self.base_row("photo-a-001", "photo-a.jpg", .10, .10, .25, .35),
            self.base_row("photo-a-002", "photo-a.jpg", .55, .20, .30, .40),
        ]
        temp, output, result = self.run_tool(rows, {"photo-a.jpg": ((800, 600), [(80, 60, 280, 270), (440, 120, 680, 360)])})
        self.addCleanup(temp.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((output / "validation-report.json").read_text())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["embedded_thumbnails"], 2)
        self.assertEqual(report["research_results"], 2)
        self.assertEqual(len(list((output / "Crops").glob("*.png"))), 2)
        self.assertEqual(len(list((output / "Thumbnails").glob("*.png"))), 2)
        with Image.open(output / "Thumbnails" / "photo-a-001_thumb.png") as image:
            self.assertEqual(image.size, (256, 256))

    def test_multiple_photos_mixed_sizes_and_excel_images(self):
        rows = [
            self.base_row("wide-001", "wide.jpg", .10, .20, .20, .40),
            self.base_row("portrait-001", "portrait.png", .25, .10, .50, .20),
            self.base_row("portrait-002", "portrait.png", .20, .60, .40, .25),
        ]
        temp, output, result = self.run_tool(rows, {
            "wide.jpg": ((1200, 400), [(120, 80, 360, 240)]),
            "portrait.png": ((400, 1200), [(100, 120, 300, 360), (80, 720, 240, 1020)]),
        })
        self.addCleanup(temp.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        workbook = output / "Stamp Inventory.xlsx"
        with zipfile.ZipFile(workbook) as archive:
            media = [name for name in archive.namelist() if name.startswith("xl/media/")]
            self.assertEqual(len(media), 3)
            drawing = ET.fromstring(archive.read("xl/drawings/drawing1.xml"))
            anchors = drawing.findall("{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}oneCellAnchor")
            self.assertEqual(len(anchors), 3)
        self.assertTrue((output / "Photos" / "wide.jpg").is_file())
        self.assertTrue((output / "Photos" / "portrait.png").is_file())
        with zipfile.ZipFile(workbook) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            self.assertIn("Collection Summary", workbook_xml)
            inventory = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
            self.assertIn("research_recommendation", inventory)
            self.assertIn("overall_confidence", inventory)

    def test_large_collection(self):
        rows = []
        for index in range(50):
            column, row = index % 10, index // 10
            rows.append(self.base_row(
                f"collection-{index + 1:03d}", "collection.jpg",
                column * .1 + .01, row * .18 + .01, .075, .14,
            ))
        temp, output, result = self.run_tool(rows, {"collection.jpg": ((2000, 1200), [])})
        self.addCleanup(temp.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((output / "validation-report.json").read_text())
        self.assertEqual(report["detected_stamps"], 50)
        self.assertEqual(report["embedded_thumbnails"], 50)
        self.assertEqual(report["collection_summary"]["detected_stamps"], 50)

    def test_duplicate_detection_reports_without_merging(self):
        rows = [
            self.base_row("same-001", "same-a.png", .1, .1, .8, .8),
            self.base_row("same-002", "same-b.png", .1, .1, .8, .8),
        ]
        photos = {
            "same-a.png": ((500, 500), [(50, 50, 450, 450)]),
            "same-b.png": ((500, 500), [(50, 50, 450, 450)]),
        }
        temp, output, result = self.run_tool(rows, photos)
        self.addCleanup(temp.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        research = json.loads((output / "research-results.json").read_text())
        self.assertIn("duplicate", research["same-001"]["duplicate_candidate"].lower())
        self.assertEqual(json.loads((output / "validation-report.json").read_text())["excel_rows"], 2)

    def test_low_quality_and_unsafe_value_language_are_handled_conservatively(self):
        row = self.base_row("poor-001", "poor.png", 0, 0, 1, 1)
        row["research_recommendation"] = "Potentially Valuable"
        row["confidence_country"] = "10%"
        temp, output, result = self.run_tool([row], {"poor.png": ((80, 80), [])})
        self.addCleanup(temp.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        research = json.loads((output / "research-results.json").read_text())["poor-001"]
        self.assertIn(research["research_recommendation"], {"Image Quality Too Low", "Low Confidence"})
        self.assertEqual(research["rescan_recommended"], "yes")

    def test_independent_confidence_scores_are_preserved(self):
        row = self.base_row("scores-001", "scores.jpg", .1, .1, .8, .8)
        row.update({"confidence_year": "74%", "confidence_series": "0.63", "ai_year": "1950s", "ai_series": "Possible test series"})
        temp, output, result = self.run_tool([row], {"scores.jpg": ((800, 800), [(80, 80, 720, 720)])})
        self.addCleanup(temp.cleanup)
        self.assertEqual(result.returncode, 0, result.stderr)
        research = json.loads((output / "research-results.json").read_text())["scores-001"]
        self.assertEqual(research["confidence_year"], .74)
        self.assertEqual(research["confidence_series"], .63)

    def test_exif_rotated_photo_uses_oriented_dimensions(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        photos_dir, output_dir = root / "Photos", root / "Output"
        photos_dir.mkdir()
        image = Image.new("RGB", (600, 400), "white")
        ImageDraw.Draw(image).rectangle((60, 40, 300, 180), fill="#6A8E3A")
        exif = Image.Exif()
        exif[274] = 6
        image.save(photos_dir / "rotated.jpg", exif=exif)
        row = self.base_row("rotated-001", "rotated.jpg", .10, .10, .50, .25)
        tsv = root / "detections.tsv"
        self.write_tsv(tsv, [row])
        result = subprocess.run([
            sys.executable, str(TOOL), "--detections", str(tsv), "--photos", str(photos_dir),
            "--template", str(TEMPLATE), "--output", str(output_dir),
        ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(output_dir / "Stamp Inventory.xlsx") as archive:
            sheet = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        self.assertIn('"image_width":400', sheet)
        self.assertIn('"image_height":600', sheet)

    def test_rejects_duplicate_stamp_ids(self):
        rows = [
            self.base_row("duplicate", "photo.jpg", .1, .1, .2, .2),
            self.base_row("duplicate", "photo.jpg", .4, .4, .2, .2),
        ]
        temp, _output, result = self.run_tool(rows, {"photo.jpg": ((500, 500), [])})
        self.addCleanup(temp.cleanup)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate stamp_id", result.stderr)

    def test_rejects_missing_photo_and_invalid_box(self):
        missing = self.base_row("missing-001", "missing.jpg", .1, .1, .2, .2)
        temp, _output, result = self.run_tool([missing], {})
        self.addCleanup(temp.cleanup)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not exist", result.stderr)

        invalid = self.base_row("invalid-001", "photo.jpg", .9, .9, .4, .4)
        temp2, _output2, result2 = self.run_tool([invalid], {"photo.jpg": ((500, 500), [])})
        self.addCleanup(temp2.cleanup)
        self.assertNotEqual(result2.returncode, 0)
        self.assertIn("exceeds image bounds", result2.stderr)


if __name__ == "__main__":
    unittest.main()
