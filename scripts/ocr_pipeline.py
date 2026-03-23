from __future__ import annotations

import argparse
import difflib
import html
import json
import math
import os
import re
import statistics
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Iterable


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
HTML_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
NONWORD_RE = re.compile(r"[^\w]+", re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")


def load_pages(results_path: Path, document_key: str | None) -> list[dict]:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    if document_key is None:
        if len(data) != 1:
            raise ValueError("results.json contains multiple document keys; pass --document-key")
        document_key = next(iter(data))
    return data[document_key]


def clean_display_text(text: str) -> str:
    text = html.unescape(text or "")
    text = HTML_BREAK_RE.sub(" ", text)
    text = HTML_TAG_RE.sub("", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_compare_text(text: str) -> str:
    text = clean_display_text(text)
    text = unicodedata.normalize("NFKC", text).lower()
    text = NONWORD_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def bbox_width(line: dict) -> float:
    return max(1.0, line["bbox"][2] - line["bbox"][0])


def bbox_height(line: dict) -> float:
    return max(1.0, line["bbox"][3] - line["bbox"][1])


def bbox_center_y(line: dict) -> float:
    return (line["bbox"][1] + line["bbox"][3]) / 2.0


def overlap_ratio(a_bbox: list[float], b_bbox: list[float]) -> tuple[float, float]:
    ax1, ay1, ax2, ay2 = a_bbox
    bx1, by1, bx2, by2 = b_bbox
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    a_w = max(1.0, ax2 - ax1)
    b_w = max(1.0, bx2 - bx1)
    a_h = max(1.0, ay2 - ay1)
    b_h = max(1.0, by2 - by1)
    return inter_w / min(a_w, b_w), inter_h / min(a_h, b_h)


def token_overlap_ratio(a: str, b: str) -> float:
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / min(len(a_tokens), len(b_tokens))


def line_priority(line: dict, page_width: float) -> float:
    text = normalize_compare_text(line.get("text") or "")
    confidence = float(line.get("confidence") or 0.0)
    width = bbox_width(line)
    alpha_chars = sum(ch.isalpha() for ch in text)
    digit_chars = sum(ch.isdigit() for ch in text)
    return (
        len(text) * 1.4
        + confidence * 60.0
        + (width / max(1.0, page_width)) * 14.0
        + alpha_chars * 0.1
        - digit_chars * 0.05
    )


def is_margin_fragment(line: dict, page_width: float, median_width: float) -> bool:
    x1, _, x2, _ = line["bbox"]
    width = bbox_width(line)
    confidence = float(line.get("confidence") or 0.0)
    compare_text = normalize_compare_text(line.get("text") or "")
    is_edge = x1 < page_width * 0.08 or x2 > page_width * 0.92
    mostly_digits = bool(compare_text) and sum(ch.isdigit() for ch in compare_text) >= math.ceil(len(compare_text) * 0.45)

    if is_edge and width < page_width * 0.18:
        return True
    if is_edge and width < min(page_width * 0.33, median_width * 0.45) and confidence < 0.72:
        return True
    if is_edge and mostly_digits and width < page_width * 0.25:
        return True
    if is_edge and width < page_width * 0.30 and confidence < 0.45:
        return True
    return False


def are_duplicate_lines(candidate: dict, kept: dict) -> bool:
    a_text = normalize_compare_text(candidate.get("text") or "")
    b_text = normalize_compare_text(kept.get("text") or "")
    if not a_text or not b_text:
        return False

    horizontal_overlap, vertical_overlap = overlap_ratio(candidate["bbox"], kept["bbox"])
    if horizontal_overlap < 0.78 or vertical_overlap < 0.35:
        return False

    similarity = difflib.SequenceMatcher(None, a_text, b_text).ratio()
    containment = (a_text in b_text or b_text in a_text) and min(len(a_text), len(b_text)) >= 24
    token_overlap = token_overlap_ratio(a_text, b_text)
    return similarity >= 0.58 or containment or token_overlap >= 0.72


def filter_text_lines(text_lines: list[dict], image_bbox: list[float] | None) -> list[dict]:
    if not text_lines:
        return []

    if image_bbox is not None and len(image_bbox) >= 3:
        page_width = max(1.0, image_bbox[2] - image_bbox[0])
    else:
        page_width = max(bbox_width(line) for line in text_lines)

    median_width = statistics.median(bbox_width(line) for line in text_lines)
    median_height = statistics.median(bbox_height(line) for line in text_lines)
    top_band_limit = min(bbox_center_y(line) for line in text_lines) + max(80.0, median_height * 3.2)
    kept: list[dict] = []
    for line in sorted(text_lines, key=lambda item: line_priority(item, page_width), reverse=True):
        compare_text = normalize_compare_text(line.get("text") or "")
        mostly_digits = bool(compare_text) and sum(ch.isdigit() for ch in compare_text) >= math.ceil(len(compare_text) * 0.45)
        if bbox_center_y(line) <= top_band_limit and mostly_digits and bbox_width(line) < page_width * 0.16:
            continue
        if is_margin_fragment(line, page_width=page_width, median_width=median_width):
            continue
        if any(are_duplicate_lines(line, existing) for existing in kept):
            continue
        kept.append(line)

    return sorted(kept, key=lambda line: (bbox_center_y(line), line["bbox"][0]))


def group_lines(text_lines: list[dict]) -> list[list[dict]]:
    if not text_lines:
        return []

    heights = [bbox_height(line) for line in text_lines]
    median_height = statistics.median(heights)
    row_threshold = max(12.0, median_height * 0.55)
    sorted_lines = sorted(text_lines, key=lambda line: (bbox_center_y(line), line["bbox"][0]))

    rows: list[list[dict]] = []
    current: list[dict] = []
    current_center: float | None = None
    for line in sorted_lines:
        y_center = bbox_center_y(line)
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
        text = clean_display_text(line.get("text") or "")
        if text:
            parts.append(text)
    row = " ".join(parts)
    return row.replace(" ,", ",").replace(" .", ".").replace(" ;", ";").replace(" :", ":")


def page_to_text(page: dict) -> str:
    filtered_lines = filter_text_lines(page.get("text_lines", []), page.get("image_bbox"))
    rows = group_lines(filtered_lines)
    if not rows:
        return ""

    row_boxes = []
    row_texts = []
    for row in rows:
        row_text = normalize_row_text(row)
        if not row_text:
            continue
        row_texts.append(row_text)
        y1 = min(line["bbox"][1] for line in row)
        y2 = max(line["bbox"][3] for line in row)
        row_boxes.append((y1, y2))

    if not row_texts:
        return ""

    heights = [max(1.0, y2 - y1) for y1, y2 in row_boxes]
    median_height = statistics.median(heights)
    paragraph_gap = max(18.0, median_height * 1.15)

    out: list[str] = []
    prev_bottom: float | None = None
    for row_text, (y1, y2) in zip(row_texts, row_boxes):
        if prev_bottom is not None and (y1 - prev_bottom) > paragraph_gap:
            out.append("")
        out.append(row_text)
        prev_bottom = y2
    return "\n".join(out).strip()


def write_raw_text(results_path: Path, output_path: Path, document_key: str | None) -> list[str]:
    pages = load_pages(results_path, document_key)
    page_texts: list[str] = []
    for page in pages:
        page_texts.append(page_to_text(page))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        for idx, text in enumerate(page_texts, start=1):
            fh.write(f"--- Page {idx} ---\n")
            fh.write(text)
            fh.write("\n\n")
    return page_texts


def ocr_cleanup_prompt(page_text: str) -> str:
    return (
        "Bereinige diesen OCR-Text konservativ. Hauptsprache ist Deutsch, es kommen aber auch "
        "Latein, Griechisch und Französisch vor. Korrigiere nur offensichtliche OCR-Fehler, "
        "Mojibake, kaputte Abstände, Trennstriche am Zeilenende, HTML-Reste, Seitenzahlen am Rand "
        "und klar doppelte Fragmente. Erhalte griechische Wörter möglichst in griechischer Schrift; "
        "wenn dieselbe Form im Text an anderer Stelle klar in griechischer Schrift vorliegt, darfst "
        "du eine offensichtliche lateinische Umschrift vorsichtig angleichen. Nichts erfinden. "
        "Wenn eine Stelle unsicher bleibt, lass sie lieber nah am OCR. Reihenfolge beibehalten. "
        "Antworte nur mit dem bereinigten Klartext.\n\n"
        f"OCR-Text:\n{page_text}"
    )


def call_lmstudio_http(page_text: str, model: str, base_url: str, timeout: int) -> str:
    import requests

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": ocr_cleanup_prompt(page_text)}],
            "temperature": 0,
            "max_tokens": 2200,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def find_default_lms() -> Path | None:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "LM Studio" / "resources" / "app" / ".webpack" / "lms.exe",
        Path("C:/Users/Mein Computer/AppData/Local/Programs/LM Studio/resources/app/.webpack/lms.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def call_lmstudio_cli(page_text: str, model: str, cli_path: Path, timeout: int) -> str:
    result = subprocess.run(
        [str(cli_path), "chat", model, "-p", ocr_cleanup_prompt(page_text)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"LM Studio CLI exited with {result.returncode}")
    return ANSI_RE.sub("", result.stdout).strip()


def revise_with_lmstudio(
    page_texts: list[str],
    output_path: Path,
    model: str,
    base_url: str,
    timeout: int,
    cli_path: Path | None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as fh:
        for idx, text in enumerate(page_texts, start=1):
            if cli_path is not None:
                revised = call_lmstudio_cli(text, model=model, cli_path=cli_path, timeout=timeout)
            else:
                revised = call_lmstudio_http(text, model=model, base_url=base_url, timeout=timeout)
            fh.write(f"--- Page {idx} ---\n")
            fh.write(revised)
            fh.write("\n\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Surya OCR JSON to ordered text and optionally revise via LM Studio.")
    parser.add_argument("--results", required=True, type=Path, help="Path to Surya results.json")
    parser.add_argument("--raw-output", required=True, type=Path, help="Path for ordered raw OCR text")
    parser.add_argument("--document-key", default=None, help="Document key inside results.json")
    parser.add_argument("--revise-output", type=Path, default=None, help="Optional path for LM Studio revised text")
    parser.add_argument("--lmstudio-base-url", default="http://127.0.0.1:1234/v1", help="LM Studio OpenAI-compatible base URL")
    parser.add_argument("--lmstudio-model", default="qwen2.5-32b-instruct", help="Model identifier to use in LM Studio")
    parser.add_argument("--lmstudio-cli", type=Path, default=None, help="Optional path to LM Studio lms.exe for CLI-based revision")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per LM Studio request in seconds")
    args = parser.parse_args()

    page_texts = write_raw_text(args.results, args.raw_output, args.document_key)

    if args.revise_output is not None:
        try:
            cli_path = args.lmstudio_cli or find_default_lms()
            revise_with_lmstudio(
                page_texts,
                output_path=args.revise_output,
                model=args.lmstudio_model,
                base_url=args.lmstudio_base_url,
                timeout=args.timeout,
                cli_path=cli_path,
            )
        except Exception as exc:
            print(f"LM Studio revision failed: {exc}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
