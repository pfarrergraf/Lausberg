from __future__ import annotations

import argparse
import io
import json
import statistics
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pypdfium2 as pdfium
from paddleocr import PaddleOCR
from PIL import Image, ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}
SUPPORTED_INPUT_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | {".pdf"}


@dataclass(slots=True)
class SourcePage:
    source_path: Path
    page_number: int
    total_pages_in_source: int
    image: Image.Image
    image_format: str


@dataclass(slots=True)
class OcrRun:
    lang: str
    engine: PaddleOCR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch OCR images/PDFs with PaddleOCR and export searchable PDF + JSON/JSONL."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input image/PDF files or folders. Folders are scanned recursively.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output") / "paddleocr_batch",
        help="Directory for OCR outputs.",
    )
    parser.add_argument(
        "--name",
        default="ocr_export",
        help="Base name for generated files.",
    )
    parser.add_argument(
        "--pdf-render-scale",
        type=float,
        default=2.0,
        help="Rasterization scale for PDF inputs before OCR. Higher improves OCR but uses more VRAM/RAM.",
    )
    parser.add_argument(
        "--langs",
        default="la,el",
        help="Comma-separated PaddleOCR recognition languages. Recommended for this corpus: la,el",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Drop OCR lines below this confidence score.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional page limit for testing.",
    )
    return parser.parse_args()


def discover_inputs(raw_inputs: list[Path]) -> list[Path]:
    discovered: list[Path] = []
    for raw_path in raw_inputs:
        path = raw_path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input does not exist: {path}")
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS:
                    discovered.append(child)
        elif path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS:
            discovered.append(path)

    unique: list[Path] = []
    seen: set[str] = set()
    for path in discovered:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)

    if not unique:
        raise ValueError("No supported input files found.")
    return unique


def iter_source_pages(input_paths: list[Path], pdf_render_scale: float, max_pages: int | None) -> Iterable[SourcePage]:
    emitted = 0
    for path in input_paths:
        suffix = path.suffix.lower()
        if suffix in SUPPORTED_IMAGE_EXTENSIONS:
            with Image.open(path) as image:
                normalized = ImageOps.exif_transpose(image)
                yield SourcePage(
                    source_path=path,
                    page_number=1,
                    total_pages_in_source=1,
                    image=normalized.convert("RGB").copy(),
                    image_format=suffix.lstrip("."),
                )
            emitted += 1
            if max_pages is not None and emitted >= max_pages:
                return
            continue

        pdf = pdfium.PdfDocument(str(path))
        total_pages = len(pdf)
        try:
            for index in range(total_pages):
                page = pdf[index]
                rendered = page.render(scale=pdf_render_scale).to_pil()
                yield SourcePage(
                    source_path=path,
                    page_number=index + 1,
                    total_pages_in_source=total_pages,
                    image=rendered.convert("RGB"),
                    image_format="pdf",
                )
                emitted += 1
                if max_pages is not None and emitted >= max_pages:
                    return
        finally:
            pdf.close()


def normalize_box(box: object) -> list[float]:
    if isinstance(box, np.ndarray):
        values = box.tolist()
    else:
        values = list(box)
    return [float(value) for value in values]


def normalize_poly(poly: object) -> list[list[float]]:
    if isinstance(poly, np.ndarray):
        points = poly.tolist()
    else:
        points = list(poly)
    return [[float(x), float(y)] for x, y in points]


def polygon_to_rect(poly: list[list[float]]) -> list[float]:
    xs = [point[0] for point in poly]
    ys = [point[1] for point in poly]
    return [min(xs), min(ys), max(xs), max(ys)]


def bbox_iou(box_a: list[float], box_b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    return inter_area / (area_a + area_b - inter_area)


def greek_char_ratio(text: str) -> float:
    letters = 0
    greek = 0
    for char in text:
        if char.isalpha():
            letters += 1
            if "GREEK" in unicodedata.name(char, ""):
                greek += 1
    if letters == 0:
        return 0.0
    return greek / letters


def script_priority(text: str, lang: str) -> tuple[int, float]:
    greek_ratio = greek_char_ratio(text)
    if lang == "el":
        return (1 if greek_ratio > 0.2 else 0, greek_ratio)
    if lang == "la":
        return (1 if greek_ratio <= 0.2 else 0, 1.0 - greek_ratio)
    return (0, 0.0)


def to_jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def compact_metadata(value: object) -> object:
    if isinstance(value, dict):
        compacted: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if "img" in lowered or "image" in lowered:
                continue
            compacted[key_text] = compact_metadata(item)
        return compacted
    if isinstance(value, np.ndarray):
        if value.ndim >= 2:
            return f"<ndarray shape={tuple(value.shape)} omitted>"
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, list):
        return [compact_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [compact_metadata(item) for item in value]
    return value


def group_lines(text_lines: list[dict]) -> list[list[dict]]:
    if not text_lines:
        return []
    heights = [max(1.0, line["bbox"][3] - line["bbox"][1]) for line in text_lines]
    median_height = statistics.median(heights)
    row_threshold = max(12.0, median_height * 0.55)
    sorted_lines = sorted(
        text_lines,
        key=lambda line: (
            (line["bbox"][1] + line["bbox"][3]) / 2.0,
            line["bbox"][0],
        ),
    )

    rows: list[list[dict]] = []
    current: list[dict] = []
    current_center: float | None = None
    for line in sorted_lines:
        y_center = (line["bbox"][1] + line["bbox"][3]) / 2.0
        if current_center is None or abs(y_center - current_center) <= row_threshold:
            current.append(line)
            current_center = statistics.mean((current_center, y_center)) if current_center is not None else y_center
        else:
            rows.append(sorted(current, key=lambda item: item["bbox"][0]))
            current = [line]
            current_center = y_center
    if current:
        rows.append(sorted(current, key=lambda item: item["bbox"][0]))
    return rows


def normalize_row_text(lines: Iterable[dict]) -> str:
    parts: list[str] = []
    for line in lines:
        text = " ".join((line.get("text") or "").split())
        if text:
            parts.append(text)
    row = " ".join(parts)
    return row.replace(" ,", ",").replace(" .", ".").replace(" ;", ";").replace(" :", ":")


def build_ordered_text(lines: list[dict]) -> str:
    rows = group_lines(lines)
    if not rows:
        return ""

    row_boxes: list[tuple[float, float]] = []
    row_texts: list[str] = []
    for row in rows:
        text = normalize_row_text(row)
        if not text:
            continue
        row_texts.append(text)
        y1 = min(line["bbox"][1] for line in row)
        y2 = max(line["bbox"][3] for line in row)
        row_boxes.append((y1, y2))

    if not row_texts:
        return ""

    heights = [max(1.0, y2 - y1) for y1, y2 in row_boxes]
    median_height = statistics.median(heights)
    paragraph_gap = max(18.0, median_height * 1.15)

    output: list[str] = []
    prev_bottom: float | None = None
    for row_text, (y1, y2) in zip(row_texts, row_boxes):
        if prev_bottom is not None and (y1 - prev_bottom) > paragraph_gap:
            output.append("")
        output.append(row_text)
        prev_bottom = y2
    return "\n".join(output).strip()


def collect_run_lines(result: dict, lang: str, min_score: float) -> list[dict]:
    lines: list[dict] = []
    rec_texts = result.get("rec_texts", [])
    rec_scores = result.get("rec_scores", [])
    rec_boxes = result.get("rec_boxes", [])
    dt_polys = result.get("dt_polys", [])

    for index, text in enumerate(rec_texts):
        score = float(rec_scores[index]) if index < len(rec_scores) else None
        if score is not None and score < min_score:
            continue

        bbox = normalize_box(rec_boxes[index]) if index < len(rec_boxes) else None
        polygon = normalize_poly(dt_polys[index]) if index < len(dt_polys) else None
        if bbox is None and polygon is not None:
            bbox = polygon_to_rect(polygon)
        if bbox is None:
            continue

        lines.append(
            {
                "text": str(text),
                "score": score,
                "bbox": bbox,
                "polygon": polygon,
                "lang": lang,
            }
        )
    return lines


def merge_multilang_lines(run_lines: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for line in sorted(run_lines, key=lambda item: ((item["bbox"][1] + item["bbox"][3]) / 2.0, item["bbox"][0])):
        best_index: int | None = None
        best_iou = 0.0
        for index, existing in enumerate(merged):
            overlap = bbox_iou(line["bbox"], existing["bbox"])
            if overlap > best_iou:
                best_iou = overlap
                best_index = index

        if best_index is None or best_iou < 0.5:
            merged.append(line)
            continue

        existing = merged[best_index]
        existing_score = float(existing["score"] or 0.0)
        candidate_score = float(line["score"] or 0.0)
        existing_priority = script_priority(existing["text"], existing["lang"])
        candidate_priority = script_priority(line["text"], line["lang"])

        choose_candidate = False
        if candidate_priority > existing_priority:
            choose_candidate = True
        elif candidate_priority == existing_priority and candidate_score > existing_score:
            choose_candidate = True

        if choose_candidate:
            merged[best_index] = line

    for index, line in enumerate(merged, start=1):
        line["index"] = index
    return merged


def ocr_page(ocr_runs: list[OcrRun], source_page: SourcePage, min_score: float) -> dict:
    raw_results: dict[str, dict] = {}
    all_lines: list[dict] = []
    image_array = np.array(source_page.image)

    for run in ocr_runs:
        result = run.engine.predict(image_array)[0]
        raw_results[run.lang] = result
        all_lines.extend(collect_run_lines(result, lang=run.lang, min_score=min_score))

    text_lines = merge_multilang_lines(all_lines)
    ordered_text = build_ordered_text(text_lines)
    primary_result = raw_results[ocr_runs[0].lang]
    return {
        "source_path": str(source_page.source_path),
        "source_name": source_page.source_path.name,
        "source_page_number": source_page.page_number,
        "source_total_pages": source_page.total_pages_in_source,
        "width": source_page.image.width,
        "height": source_page.image.height,
        "image_format": source_page.image_format,
        "ocr_langs": [run.lang for run in ocr_runs],
        "ocr_model_settings": compact_metadata(primary_result.get("model_settings", {})),
        "doc_preprocessor_res": compact_metadata(primary_result.get("doc_preprocessor_res", {})),
        "ordered_text": ordered_text,
        "text_lines": text_lines,
    }


def find_font_path() -> Path | None:
    candidates = [
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def register_overlay_font() -> str:
    font_path = find_font_path()
    if font_path is None:
        return "Helvetica"
    font_name = "OverlayUnicode"
    try:
        pdfmetrics.getFont(font_name)
    except KeyError:
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    return font_name


def save_searchable_pdf(output_path: Path, pages: list[dict], page_images: list[Image.Image]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pageCompression=1)
    font_name = register_overlay_font()

    for page_data, image in zip(pages, page_images):
        page_width = page_data["width"]
        page_height = page_data["height"]
        pdf.setPageSize((page_width, page_height))

        image_bytes = io.BytesIO()
        image.save(image_bytes, format="JPEG", quality=95)
        image_bytes.seek(0)
        pdf.drawImage(ImageReader(image_bytes), 0, 0, width=page_width, height=page_height, preserveAspectRatio=False)

        text_object = pdf.beginText()
        text_object.setTextRenderMode(3)
        text_object.setFillColorRGB(0, 0, 0)

        for line in page_data["text_lines"]:
            text = line["text"].strip()
            if not text:
                continue
            x1, y1, x2, y2 = line["bbox"]
            width = max(1.0, x2 - x1)
            height = max(1.0, y2 - y1)
            font_size = max(6.0, height * 0.72)

            text_object.setFont(font_name, font_size)
            text_width = max(1.0, pdfmetrics.stringWidth(text, font_name, font_size))
            text_object.setHorizScale((width / text_width) * 100.0)

            baseline_y = page_height - y2 + (height - font_size) * 0.65
            text_object.setTextOrigin(x1, baseline_y)
            text_object.textLine(text)

        pdf.drawText(text_object)
        pdf.showPage()

    pdf.save()


def save_json(output_path: Path, payload: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_jsonl(output_path: Path, pages: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for page in pages:
            handle.write(json.dumps(page, ensure_ascii=False))
            handle.write("\n")


def save_text(output_path: Path, pages: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for index, page in enumerate(pages, start=1):
            handle.write(f"--- Page {index}: {page['source_name']}#{page['source_page_number']} ---\n")
            handle.write(page["ordered_text"])
            handle.write("\n\n")


def parse_langs(raw_langs: str) -> list[str]:
    langs = [item.strip() for item in raw_langs.split(",") if item.strip()]
    if not langs:
        raise ValueError("At least one OCR language must be provided.")
    return langs


def build_ocr_engines(langs: list[str]) -> list[OcrRun]:
    return [OcrRun(lang=lang, engine=PaddleOCR(lang=lang)) for lang in langs]


def main() -> int:
    args = parse_args()
    input_paths = discover_inputs(args.inputs)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    pages: list[dict] = []
    page_images: list[Image.Image] = []

    langs = parse_langs(args.langs)
    ocr_runs = build_ocr_engines(langs)
    created_at = datetime.now(UTC).isoformat()

    try:
        for index, source_page in enumerate(
            iter_source_pages(input_paths, pdf_render_scale=args.pdf_render_scale, max_pages=args.max_pages),
            start=1,
        ):
            print(
                f"OCR {index}: {source_page.source_path.name} page {source_page.page_number}/"
                f"{source_page.total_pages_in_source} with langs={','.join(langs)}"
            )
            page_images.append(source_page.image.copy())
            pages.append(ocr_page(ocr_runs, source_page, min_score=args.min_score))
            source_page.image.close()

        if not pages:
            raise ValueError("No pages were processed.")

        base_name = args.name
        searchable_pdf_path = output_dir / f"{base_name}.searchable.pdf"
        json_path = output_dir / f"{base_name}.json"
        jsonl_path = output_dir / f"{base_name}.jsonl"
        text_path = output_dir / f"{base_name}.txt"

        payload = {
            "created_at_utc": created_at,
            "input_files": [str(path) for path in input_paths],
            "page_count": len(pages),
            "pages": pages,
        }

        save_searchable_pdf(searchable_pdf_path, pages, page_images)
        save_json(json_path, payload)
        save_jsonl(jsonl_path, pages)
        save_text(text_path, pages)

        print(f"Searchable PDF: {searchable_pdf_path}")
        print(f"JSON: {json_path}")
        print(f"JSONL: {jsonl_path}")
        print(f"Text: {text_path}")
        return 0
    finally:
        for image in page_images:
            image.close()


if __name__ == "__main__":
    raise SystemExit(main())
