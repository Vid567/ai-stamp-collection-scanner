#!/usr/bin/env python3
"""Deterministic Phase 2 enrichment for stamp crops.

Identification facts are accepted only from the existing vision-AI TSV output.
This module adds local image-quality measurements, confidence aggregation,
collection-level similarity hints and conservative research recommendations.
It never invents catalogue numbers, rarity or monetary values.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageFilter, ImageOps, ImageStat


CONFIDENCE_FIELDS = [
    "confidence_country", "confidence_year", "confidence_theme",
    "confidence_category", "confidence_series", "confidence_denomination",
]
RECOMMENDATIONS = {
    "Very Common", "Common", "Worth Checking", "Interesting",
    "Potentially Valuable", "Rare Characteristics Detected",
    "Manual Review Recommended", "Low Confidence",
    "Image Quality Too Low", "Unknown",
}


def parse_confidence(value: str | float | int | None) -> float | None:
    """Return confidence as a 0..1 value, accepting decimal or percent input."""
    if value in (None, ""):
        return None
    labels = {"high": 0.85, "medium": 0.60, "low": 0.30}
    if str(value).strip().lower() in labels:
        return labels[str(value).strip().lower()]
    try:
        number = float(str(value).strip().rstrip("%"))
    except ValueError:
        return None
    if "%" in str(value) or number > 1:
        number /= 100
    return max(0.0, min(1.0, number)) if math.isfinite(number) else None


def _laplacian_variance(image: Image.Image) -> float:
    grey = ImageOps.grayscale(image).resize((min(image.width, 512), min(image.height, 512)))
    edges = grey.filter(ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1))
    return float(ImageStat.Stat(edges).var[0])


def _dhash(image: Image.Image) -> int:
    grey = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(grey.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return value


def _dominant_colour(image: Image.Image) -> str:
    sample = image.convert("RGB").resize((64, 64)).quantize(colors=5)
    palette = sample.getpalette() or []
    colour_index = max(sample.getcolors() or [(0, 0)])[1]
    red, green, blue = palette[colour_index * 3:colour_index * 3 + 3]
    if max(red, green, blue) - min(red, green, blue) < 24:
        return "light neutral" if (red + green + blue) / 3 > 170 else "dark neutral"
    channels = {"red": red, "green": green, "blue": blue}
    return max(channels, key=channels.get)


@dataclass
class ResearchResult:
    """Auditable Phase 2 fields attached to one Phase 1 detection."""

    record_id: str
    ai_country: str = ""
    confidence_country: float | None = None
    ai_year: str = ""
    confidence_year: float | None = None
    ai_theme: str = ""
    confidence_theme: float | None = None
    ai_category: str = ""
    confidence_category: float | None = None
    ai_series: str = ""
    confidence_series: float | None = None
    ai_denomination: str = ""
    confidence_denomination: float | None = None
    visible_text: str = ""
    language: str = ""
    ai_purpose: str = ""
    visual_traits: str = ""
    estimated_period: str = ""
    dominant_colour: str = ""
    image_quality_score: float = 0.0
    image_quality: str = ""
    quality_flags: str = ""
    rescan_recommended: str = "no"
    duplicate_candidate: str = ""
    duplicate_similarity: float | None = None
    research_recommendation: str = "Unknown"
    overall_confidence: float = 0.0
    research_notes: str = ""
    identification_confidence: float = 0.0
    period_confidence: float = 0.0
    research_confidence: float = 0.0
    country_reasoning: str = ""
    interest_score: int = 0
    interest_label: str = "Low Interest"
    research_priority: str = "Low"
    possible_features: str = ""
    interest_reasons: str = ""
    research_checklist: str = ""
    duplicate_group: str = ""
    grouping: str = "single"
    collector_notes: str = ""
    decision_path: str = ""
    decision_source: str = "local rules + supplied AI observations"
    perceptual_hash: int = field(default=0, repr=False)

    def excel_values(self) -> dict[str, Any]:
        values = asdict(self)
        values.pop("perceptual_hash", None)
        return values


def analyse_crop(record_id: str, row: dict[str, str], crop_path: Path, touches_edge: bool) -> ResearchResult:
    """Measure crop quality once and conservatively combine supplied AI fields."""
    with Image.open(crop_path) as raw:
        image = raw.convert("RGB")
        sharpness = _laplacian_variance(image)
        grey = ImageOps.grayscale(image)
        contrast = float(ImageStat.Stat(grey).stddev[0])
        brightness = float(ImageStat.Stat(grey).mean[0])
        resolution = min(1.0, min(image.size) / 500)
        sharpness_score = min(1.0, sharpness / 900)
        contrast_score = min(1.0, contrast / 55)
        lighting_score = max(0.0, 1.0 - abs(brightness - 135) / 135)
        score = 0.40 * sharpness_score + 0.25 * contrast_score + 0.20 * resolution + 0.15 * lighting_score
        flags: list[str] = []
        if sharpness_score < 0.30:
            flags.append("blur or low detail")
        if contrast_score < 0.30:
            flags.append("low contrast")
        if brightness < 55:
            flags.append("underexposed")
        elif brightness > 225:
            flags.append("overexposed")
        if resolution < 0.35:
            flags.append("low resolution")
        if touches_edge:
            flags.append("crop touches source edge; partial stamp possible")
            score *= 0.8
        score = round(max(0.0, min(1.0, score)), 3)
        label = "Good" if score >= 0.72 else "Usable" if score >= 0.48 else "Poor"

        result = ResearchResult(
            record_id=record_id,
            ai_country=(row.get("ai_country") or row.get("country_normalized") or "").strip(),
            ai_year=(row.get("ai_year") or row.get("year") or "").strip(),
            ai_theme=(row.get("ai_theme") or row.get("theme") or "").strip(),
            ai_category=(row.get("ai_category") or row.get("stamp_type") or "").strip(),
            ai_series=(row.get("ai_series") or "").strip(),
            ai_denomination=(row.get("ai_denomination") or " ".join(filter(None, [row.get("face_value", ""), row.get("value_unit", "")]))).strip(),
            visible_text=(row.get("visible_text") or row.get("country_as_printed") or "").strip(),
            language=(row.get("language") or "").strip(),
            ai_purpose=(row.get("ai_purpose") or row.get("stamp_type") or "").strip(),
            visual_traits=(row.get("visual_traits") or "").strip(),
            estimated_period=(row.get("estimated_period") or "").strip(),
            dominant_colour=(row.get("dominant_colour") or row.get("colour") or _dominant_colour(image)).strip(),
            image_quality_score=score,
            image_quality=label,
            quality_flags="; ".join(flags),
            rescan_recommended="yes" if score < 0.48 else "no",
            perceptual_hash=_dhash(image),
        )

    for name in CONFIDENCE_FIELDS:
        setattr(result, name, parse_confidence(row.get(name)))
    supplied = [getattr(result, name) for name in CONFIDENCE_FIELDS if getattr(result, name) is not None]
    fallback = parse_confidence(row.get("confidence_score")) or parse_confidence(row.get("id_confidence"))
    if not supplied and fallback is not None:
        supplied = [fallback]
    result.overall_confidence = round((sum(supplied) / len(supplied)) * (0.75 + 0.25 * score), 3) if supplied else 0.0

    requested = (row.get("research_recommendation") or "").strip()
    rare = (row.get("rare_characteristics") or "").strip()
    if score < 0.48:
        recommendation = "Image Quality Too Low"
    elif result.overall_confidence < 0.40:
        recommendation = "Low Confidence"
    elif rare:
        recommendation = "Rare Characteristics Detected"
    elif requested in RECOMMENDATIONS:
        recommendation = "Worth Checking" if requested == "Potentially Valuable" else requested
    elif result.overall_confidence >= 0.75 and result.ai_country:
        recommendation = "Worth Checking" if row.get("research_priority") == "high" else "Common"
    else:
        recommendation = "Manual Review Recommended"
    result.research_recommendation = recommendation
    notes = []
    if result.rescan_recommended == "yes":
        notes.append("Better photograph recommended")
    if requested == "Potentially Valuable":
        notes.append("Value language removed; catalogue or expert evidence required")
    if rare:
        notes.append(f"AI-reported characteristic requiring verification: {rare}")
    result.research_notes = "; ".join(notes)
    result.identification_confidence = result.overall_confidence
    result.period_confidence = result.confidence_year or parse_confidence(row.get("confidence_period")) or 0.0
    evidence = []
    for field, label in (("visible_text", "visible text"), ("language", "language"),
                         ("currency", "currency"), ("symbols", "symbols"),
                         ("coat_of_arms", "coat of arms"), ("monarch", "monarch"),
                         ("visual_traits", "design/style")):
        if (row.get(field) or "").strip():
            evidence.append(label)
    result.country_reasoning = (
        "Country suggestion based on " + ", ".join(evidence) if evidence
        else "No independent country evidence supplied; manual verification required"
    )
    _apply_collector_insights(result, row)
    return result


def _year_floor(*values: str) -> int | None:
    for value in values:
        match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", value or "")
        if match:
            return int(match.group(1))
    return None


def _apply_collector_insights(result: ResearchResult, row: dict[str, str]) -> None:
    """Create a transparent research score from observable/supplied indicators only."""
    text = " ".join(str(row.get(key, "")) for key in row).lower()
    reasons: list[str] = []
    features: list[str] = []
    checklist = {"Compare with a trusted catalogue", "Verify issue date"}
    score = 0
    year = _year_floor(result.ai_year, result.estimated_period, row.get("year", ""))
    if year and year < 1900:
        score += 24; reasons.append("appears to pre-date 1900; date needs verification")
    elif year and year < 1945:
        score += 12; reasons.append("appears to be an earlier issue")
    indicators = [
        (("overprint", "overprinted"), 18, "possible overprint", "Inspect overprint typography and ink"),
        (("surcharge",), 16, "possible surcharge", "Verify surcharge against catalogue varieties"),
        (("occupation",), 18, "possible occupation issue", "Verify issuing authority and period"),
        (("colony", "colonial"), 12, "possible colonial issue", "Check issuing territory and parent administration"),
        (("official", "service stamp"), 11, "possible official/service stamp", "Confirm official or service markings"),
        (("airmail", "air mail"), 9, "possible airmail issue", "Compare airmail inscription and issue date"),
        (("postage due",), 11, "possible postage-due issue", "Confirm postage-due purpose"),
        (("commemorative",), 5, "commemorative design reported", "Confirm commemorative event and date"),
        (("watermark",), 8, "watermark may distinguish varieties", "Verify watermark"),
        (("perforation", "imperforate"), 8, "perforation characteristic reported", "Measure perforation"),
        (("colour variation", "color variation", "shade"), 8, "possible colour or shade variation", "Compare colour shade under neutral light"),
        (("unusual cancellation", "uncommon cancellation", "special cancellation"), 10, "cancellation may deserve inspection", "Inspect cancellation"),
        (("variety", "error", "misprint"), 14, "possible visible variety; specialist confirmation required", "Compare reported variety with specialist reference"),
        (("complete set",), 10, "possible complete set", "Verify set completeness"),
    ]
    for needles, weight, reason, action in indicators:
        if any(needle in text for needle in needles):
            score += weight; reasons.append(reason); features.append(reason.split(";", 1)[0]); checklist.add(action)
    quantity = str(row.get("quantity", "1")).strip()
    grouping = (row.get("grouping") or row.get("format") or "").strip().lower()
    if "block" in grouping or "block" in text:
        result.grouping = "block"; score += 10; reasons.append("multiple appears to be a block"); checklist.add("Verify block layout and selvage")
    elif "strip" in grouping or "strip" in text:
        result.grouping = "strip"; score += 7; reasons.append("multiple appears to be a strip")
    elif "pair" in grouping or quantity == "2":
        result.grouping = "pair"; score += 5; reasons.append("appears to be a pair")
    condition = (row.get("condition") or "").lower()
    if any(term in condition for term in ("fault", "tear", "thin", "crease", "damaged")):
        reasons.append("condition issue visible or reported"); checklist.add("Inspect condition, repairs and faults")
    if "used" not in condition:
        checklist.add("Check gum and hinge condition if accessible")
    checklist.add("Check paper type")
    if result.image_quality == "Poor":
        score = min(score, 39); reasons.insert(0, "image quality limits reliable research"); checklist.add("Retake a sharper, evenly lit photograph")
    confidence_factor = 0.55 + 0.45 * result.overall_confidence
    result.interest_score = max(0, min(100, round(score * confidence_factor)))
    result.interest_label = ("Exceptional Research Candidate" if result.interest_score >= 75 else
                             "High Interest" if result.interest_score >= 50 else
                             "Medium Interest" if result.interest_score >= 25 else "Low Interest")
    result.research_priority = "Exceptional" if result.interest_score >= 75 else "High" if result.interest_score >= 50 else "Medium" if result.interest_score >= 25 else "Low"
    result.possible_features = "; ".join(dict.fromkeys(features))
    result.interest_reasons = "; ".join(dict.fromkeys(reasons)) or "no supported research indicators detected"
    result.research_checklist = " | ".join(f"□ {item}" for item in sorted(checklist))
    evidence_count = len(reasons)
    result.research_confidence = round(min(1.0, (0.35 + 0.08 * evidence_count) * (0.65 + 0.35 * result.image_quality_score)), 3)
    result.collector_notes = (row.get("collector_notes") or row.get("notes") or "").strip()
    result.decision_path = f"observable indicators={evidence_count}; quality={result.image_quality_score:.3f}; identification={result.overall_confidence:.3f}; score={result.interest_score}"


def mark_duplicates(results: list[ResearchResult]) -> None:
    """Report perceptual similarity without merging or asserting identity."""
    links: list[tuple[str, str]] = []
    for index, left in enumerate(results):
        best: tuple[int, ResearchResult] | None = None
        for right in results[index + 1:]:
            distance = (left.perceptual_hash ^ right.perceptual_hash).bit_count()
            if best is None or distance < best[0]:
                best = (distance, right)
        if best and best[0] <= 12:
            distance, right = best
            similarity = round(1 - distance / 64, 3)
            label = "Likely duplicate" if distance <= 5 else "Very similar"
            left.duplicate_candidate = f"{label}: {right.record_id}"
            left.duplicate_similarity = similarity
            if not right.duplicate_candidate:
                right.duplicate_candidate = f"{label}: {left.record_id}"
                right.duplicate_similarity = similarity
            links.append((left.record_id, right.record_id))
    parent = {result.record_id: result.record_id for result in results}
    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]; item = parent[item]
        return item
    for left, right in links:
        a, b = find(left), find(right)
        if a != b: parent[b] = a
    groups: dict[str, list[ResearchResult]] = {}
    for result in results:
        if result.duplicate_candidate:
            groups.setdefault(find(result.record_id), []).append(result)
    for number, members in enumerate(groups.values(), start=1):
        for result in members:
            result.duplicate_group = f"DUP-{number:03d}"
            if result.grouping == "single": result.grouping = "duplicate"


def collection_summary(results: Iterable[ResearchResult], photo_count: int, processing_seconds: float) -> dict[str, Any]:
    results = list(results)
    countries = Counter(r.ai_country for r in results if r.ai_country)
    themes = Counter(r.ai_theme for r in results if r.ai_theme)
    recommendations = Counter(r.research_recommendation for r in results)
    duplicates = sum(bool(r.duplicate_candidate) for r in results)
    return {
        "uploaded_photographs": photo_count,
        "detected_stamps": len(results),
        "average_confidence": round(sum(r.overall_confidence for r in results) / len(results), 3),
        "countries_detected": len(countries),
        "top_countries": countries.most_common(5),
        "themes_detected": len(themes),
        "top_themes": themes.most_common(5),
        "duplicate_candidates": duplicates,
        "unknown_stamps": sum(not r.ai_country for r in results),
        "low_quality_images": sum(r.image_quality == "Poor" for r in results),
        "manual_review_count": sum(r.research_recommendation in {"Manual Review Recommended", "Low Confidence", "Image Quality Too Low"} for r in results),
        "research_candidates": sum(r.research_recommendation in {"Worth Checking", "Interesting", "Rare Characteristics Detected"} for r in results),
        "average_image_quality": round(sum(r.image_quality_score for r in results) / len(results), 3),
        "top_recommendations": recommendations.most_common(5),
        "estimated_periods": Counter(r.estimated_period or r.ai_year for r in results if r.estimated_period or r.ai_year).most_common(10),
        "interest_levels": Counter(r.interest_label for r in results).most_common(),
        "high_interest_candidates": sum(r.interest_score >= 50 for r in results),
        "exceptional_research_candidates": sum(r.interest_score >= 75 for r in results),
        "duplicate_groups": len({r.duplicate_group for r in results if r.duplicate_group}),
        "processing_seconds": round(processing_seconds, 3),
    }
