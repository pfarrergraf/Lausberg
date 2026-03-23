from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
import requests
from paddleocr import PPStructureV3, PaddleOCR, PaddleOCRVL


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}

ASSIST_LANGS = ("de", "la", "el", "fr") # German, Latin, Greek, French assist OCRs. French is less critical but can help with occasional French text in some books.


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Digitize books with PaddleOCR into Markdown/JSON, with optional LM Studio cleanup."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF/image files or folders")
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "book_digitize")
    parser.add_argument("--name", default="book")
    parser.add_argument(
        "--lang",
        default="de",
        help="Primary OCR language for PPStructureV3. Use a single PaddleOCR language such as 'de' or 'la'. For mixed German/Latin/Greek/French books, keep a single primary language here and rely on the assist OCR passes.",
    )
    parser.add_argument(
        "--engine",
        choices=("ppstructure", "ocrvl"),
        default="ppstructure",
        help="OCR engine: 'ppstructure' for the stable default on text-heavy pages, 'ocrvl' for the heavier VL parser on harder layouts. On this machine, 'ocrvl' is usable but slower.",
    )
    parser.add_argument(
        "--pipeline-version",
        default="v1.5",
        help="PaddleOCR-VL pipeline version used with --engine ocrvl.",
    )
    parser.add_argument(
        "--fallback-engine",
        choices=("none", "ppstructure"),
        default="ppstructure",
        help="Fallback engine when the selected engine fails. Recommended: keep 'ppstructure' as fallback for long runs.",
    )
    parser.add_argument(
        "--format-block-content",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable Paddle block-content formatting for cleaner Markdown structure. Disable only for debugging raw layout output.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional page limit for testing.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Rasterization DPI for PDF pages. 300 is the balanced default; try 400 for difficult historical pages with very small print.",
    )
    parser.add_argument(
        "--revise",
        action="store_true",
        help="Run a conservative LM Studio cleanup pass over the Markdown.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
        help="Max characters per revision chunk. Smaller is more stable for LM Studio.",
    )
    parser.add_argument(
        "--no-assist",
        action="store_true",
        help="Disable secondary assist OCR passes (de/la/el/fr).",
    )
    parser.add_argument(
        "--lmstudio-transport",
        choices=("http", "cli"),
        default="http",
        help="Use LM Studio via HTTP or CLI. HTTP is strongly recommended on Windows.",
    )
    parser.add_argument("--lmstudio-base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument(
        "--lmstudio-model",
        default="qwen_qwen3.5-35b-a3b",
        help="LM Studio model id, not the GGUF filename. Example: 'qwen_qwen3.5-35b-a3b'.",
    )
    parser.add_argument("--lmstudio-cli", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=1200)
    return parser.parse_args()


def discover_inputs(raw_inputs: list[Path]) -> list[Path]:
    discovered: list[Path] = []
    for raw in raw_inputs:
        path = raw.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input does not exist: {path}")
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    discovered.append(child)
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
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


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def find_default_lms() -> Path | None:
    candidates = [
        Path.home() / ".lmstudio" / "bin" / "lms.exe",
        Path.home() / ".lmstudio" / "bin" / "lms",
        Path.home() / ".local" / "bin" / "lms",
        Path("/usr/local/bin/lms"),
        Path("/usr/bin/lms"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    found = shutil.which("lms")
    return Path(found) if found else None


def call_lmstudio_cli(prompt: str, model: str, cli_path: Path, timeout: int) -> str:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp:
        tmp.write(prompt)
        tmp_path = Path(tmp.name)

    try:
        cmd = [
            str(cli_path),
            "chat",
            "--model",
            model,
            "--file",
            str(tmp_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.stdout.strip()
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def call_lmstudio_http(prompt: str, model: str, base_url: str, timeout: int) -> str:
    model = resolve_lmstudio_model(model=model, base_url=base_url, timeout=timeout)
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a conservative OCR cleanup assistant. "
                    "Never paraphrase. Never translate. Never invent text. "
                    "Return only cleaned markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "top_p": 1,
        "stream": False,
    }
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def normalize_model_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def resolve_lmstudio_model(model: str, base_url: str, timeout: int) -> str:
    url = base_url.rstrip("/") + "/models"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return model

    items = data.get("data") or []
    ids = [item.get("id", "") for item in items if item.get("id")]
    if not ids:
        return model
    if model in ids:
        return model

    target = normalize_model_name(model)
    normalized_ids = {normalize_model_name(item_id): item_id for item_id in ids}
    if target in normalized_ids:
        return normalized_ids[target]

    for item_id in ids:
        normalized = normalize_model_name(item_id)
        if target in normalized or normalized in target:
            return item_id
    return model


def build_pipeline(engine: str, lang: str, format_block_content: bool, pipeline_version: str) -> object:
    if engine == "ocrvl":
        return PaddleOCRVL(
            pipeline_version=pipeline_version,
            use_chart_recognition=False,
            use_seal_recognition=False,
            format_block_content=format_block_content,
            merge_layout_blocks=True,
            use_queues=False,
        )
    return PPStructureV3(
        lang=lang,
        use_table_recognition=False,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
        format_block_content=format_block_content,
    )


def build_assist_ocrs(enabled: bool) -> dict[str, PaddleOCR]:
    if not enabled:
        return {}
    ocrs: dict[str, PaddleOCR] = {}
    for lang in ASSIST_LANGS:
        ocrs[lang] = PaddleOCR(lang=lang)
    return ocrs


def render_pdf_to_images(pdf_path: Path, out_dir: Path, dpi: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    scale = dpi / 72.0
    image_paths: list[Path] = []

    for page_index in range(len(pdf)):
        page = pdf[page_index]
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        out_path = out_dir / f"{pdf_path.stem}_p{page_index + 1:04d}.png"
        pil_image.save(out_path)
        image_paths.append(out_path)

    return image_paths


def crop_to_page_region(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    white_ratio = float(np.mean(thresh > 127))
    if white_ratio < 0.5:
        thresh = cv2.bitwise_not(thresh)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return image

    h, w = image.shape[:2]
    best_rect = None
    best_area = 0

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if area > best_area and cw > 0.45 * w and ch > 0.45 * h:
            best_rect = (x, y, cw, ch)
            best_area = area

    if best_rect is None:
        return image

    x, y, cw, ch = best_rect
    pad_x = int(cw * 0.02)
    pad_y = int(ch * 0.02)
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(w, x + cw + pad_x)
    y1 = min(h, y + ch + pad_y)
    return image[y0:y1, x0:x1]


def deskew_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))

    if len(coords) < 100:
        return image

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    angle = -angle

    if abs(angle) < 0.25:
        return image

    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def normalize_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
    sharpened = cv2.addWeighted(gray, 1.5, blur, -0.5, 0)

    bw = cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        12,
    )
    return cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)


def preprocess_image_file(input_path: Path, output_path: Path) -> Path:
    image = cv2.imread(str(input_path))
    if image is None:
        raise ValueError(f"Failed to read image: {input_path}")

    image = crop_to_page_region(image)
    image = deskew_image(image)
    image = normalize_image(image)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(output_path), image)
    if not ok:
        raise ValueError(f"Failed to write preprocessed image: {output_path}")
    return output_path


def prepare_input_pages(inputs: list[Path], temp_root: Path, dpi: int, max_pages: int | None) -> list[dict]:
    prepared: list[dict] = []
    page_counter = 0

    for input_path in inputs:
        suffix = input_path.suffix.lower()
        if suffix == ".pdf":
            pdf_img_dir = temp_root / "rendered" / input_path.stem
            rendered_pages = render_pdf_to_images(input_path, pdf_img_dir, dpi=dpi)
            for source_page_index, rendered_path in enumerate(rendered_pages, start=1):
                page_counter += 1
                if max_pages is not None and page_counter > max_pages:
                    return prepared
                pre_path = temp_root / "preprocessed" / f"{page_counter:06d}_{rendered_path.name}"
                preprocess_image_file(rendered_path, pre_path)
                prepared.append(
                    {
                        "page_number": page_counter,
                        "source_file": input_path,
                        "source_page_index": source_page_index,
                        "input_path": pre_path,
                    }
                )
        else:
            page_counter += 1
            if max_pages is not None and page_counter > max_pages:
                return prepared
            pre_path = temp_root / "preprocessed" / f"{page_counter:06d}_{input_path.name}"
            preprocess_image_file(input_path, pre_path)
            prepared.append(
                {
                    "page_number": page_counter,
                    "source_file": input_path,
                    "source_page_index": 1,
                    "input_path": pre_path,
                }
            )
    return prepared


def run_pipeline_on_page(
    pipeline: object,
    engine: str,
    format_block_content: bool,
    page_path: Path,
) -> object:
    if engine == "ocrvl":
        predict_kwargs = {
            "use_chart_recognition": False,
            "use_seal_recognition": False,
            "format_block_content": format_block_content,
            "merge_layout_blocks": True,
        }
    else:
        predict_kwargs = {
            "use_table_recognition": False,
            "use_formula_recognition": False,
            "use_chart_recognition": False,
            "use_seal_recognition": False,
            "format_block_content": format_block_content,
        }

    results = list(pipeline.predict(str(page_path), **predict_kwargs))
    if not results:
        raise RuntimeError(f"No OCR result returned for {page_path}")
    return results[0]


def extract_markdown_text(result: object) -> str:
    markdown = getattr(result, "markdown", None) or {}
    return (markdown.get("markdown_texts") or "").strip()


def format_page_header(page_number: int, source_file: Path, source_page_index: int) -> str:
    return f"<!-- Page {page_number} | source={source_file.name} | source_page={source_page_index} -->"


def normalize_assist_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        text = re.sub(r"\s+", " ", text)
        cleaned.append(text)
    return cleaned


def extract_assist_texts(assist_ocrs: dict[str, PaddleOCR], input_path: Path) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for lang, ocr in assist_ocrs.items():
        try:
            pages = list(
                ocr.predict(
                    str(input_path),
                    use_textline_orientation=True,
                    return_word_box=False,
                )
            )
        except Exception as exc:
            print(f"Assist OCR failed for {input_path.name} [{lang}]: {exc}", file=sys.stderr)
            continue

        all_lines: list[str] = []
        for page in pages:
            rec_texts = page.get("rec_texts") or []
            all_lines.extend(normalize_assist_lines(rec_texts))

        if all_lines:
            outputs[lang] = "\n".join(all_lines)
    return outputs


def compress_assist_texts(assist_texts: dict[str, str], max_lines_per_lang: int = 10) -> dict[str, str]:
    compressed: dict[str, str] = {}
    greek_pattern = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")

    for lang, text in assist_texts.items():
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lang == "el":
            filtered = [ln for ln in lines if greek_pattern.search(ln)]
            if not filtered:
                filtered = lines
            lines = filtered
        else:
            lines = [ln for ln in lines if len(ln) > 20]

        compressed_lines = lines[:max_lines_per_lang]
        if compressed_lines:
            compressed[lang] = "\n".join(compressed_lines)

    return compressed


def collapse_hyphenation(text: str) -> str:
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text


def split_markdown_blocks(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    blocks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) > max_chars:
            if current:
                blocks.append(current)
                current = ""

            lines = para.splitlines()
            chunk = ""
            for line in lines:
                candidate = f"{chunk}\n{line}".strip() if chunk else line
                if len(candidate) <= max_chars:
                    chunk = candidate
                else:
                    if chunk:
                        blocks.append(chunk)
                    chunk = line
            if chunk:
                blocks.append(chunk)
            continue

        if not current:
            current = para
            continue

        candidate = current + "\n\n" + para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            blocks.append(current)
            current = para

    if current:
        blocks.append(current)

    return blocks


def is_probable_footnote_block(block: str) -> bool:
    short_lines = [ln for ln in block.splitlines() if ln.strip()]
    if not short_lines:
        return False
    starts_with_note = sum(bool(re.match(r"^\s*[\(\[]?\d+[\)\].]?\s", ln)) for ln in short_lines)
    avg_len = sum(len(ln) for ln in short_lines) / max(1, len(short_lines))
    return starts_with_note >= 1 and avg_len < 120


def build_revision_prompt(block_text: str, assist_texts: dict[str, str], block_kind: str) -> str:
    prompt = (
        "Bereinige den folgenden OCR-Markdowntext streng konservativ.\n\n"
        "Dokumenttyp: wissenschaftliches geisteswissenschaftliches Buch.\n"
        "Sprachen: vor allem Deutsch, Latein, Griechisch, vereinzelt Französisch.\n\n"
        "Regeln:\n"
        "1. Keine Zusammenfassung, keine Übersetzung, keine Paraphrase.\n"
        "2. Nichts erfinden, nichts ergänzen.\n"
        "3. Korrigiere nur offensichtliche OCR-Fehler, kaputte Worttrennungen, falsche Leerzeichen, Mojibake und klar erkennbare Zeichenfehler.\n"
        "4. Erhalte vorhandenes Markdown und Absatzstruktur.\n"
        "5. Fußnoten dürfen nicht in den Fließtext verschoben werden.\n"
        "6. Griechische Wörter sollen in griechischer Schrift stehen, aber nur wenn die Hilfs-OCR das klar stützt.\n"
        "7. Latein bleibt Latein. Deutsch bleibt Deutsch. Nicht modernisieren.\n"
        "8. Unsichere Stellen konservativ belassen.\n"
        "9. Antworte nur mit dem bereinigten Markdowntext.\n\n"
        f"Blocktyp: {block_kind}\n\n"
        "Haupt-OCR:\n"
        f"{block_text}\n"
    )

    if assist_texts:
        prompt += "\nHilfs-OCR:\n"
        for lang in ("de", "la", "el"):
            if lang in assist_texts:
                prompt += f"\n[{lang}]\n{assist_texts[lang]}\n"
    return prompt


def revise_markdown_block(
    block_text: str,
    assist_texts: dict[str, str],
    model: str,
    base_url: str,
    timeout: int,
    cli_path: Path | None,
) -> str:
    block_kind = "footnote" if is_probable_footnote_block(block_text) else "body"
    prompt = build_revision_prompt(block_text, assist_texts, block_kind=block_kind)

    try:
        if cli_path is not None:
            raw = call_lmstudio_cli(
                prompt=prompt,
                model=model,
                cli_path=cli_path,
                timeout=timeout,
            )
        else:
            raw = call_lmstudio_http(
                prompt=prompt,
                model=model,
                base_url=base_url,
                timeout=timeout,
            )
    except Exception as exc:
        print(f"LM Studio revision failed, falling back to HTTP: {exc}", file=sys.stderr)
        raw = call_lmstudio_http(
            prompt=prompt,
            model=model,
            base_url=base_url,
            timeout=timeout,
        )

    cleaned_lines = [line for line in raw.splitlines() if not line.strip().startswith("Loading ")]
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned if cleaned else block_text


def revise_markdown_text(
    text: str,
    assist_texts: dict[str, str],
    model: str,
    base_url: str,
    timeout: int,
    cli_path: Path | None,
    chunk_size: int,
) -> str:
    text = collapse_hyphenation(text)
    assist_texts = compress_assist_texts(assist_texts, max_lines_per_lang=10)
    blocks = split_markdown_blocks(text, max_chars=chunk_size)
    if not blocks:
        return text.strip()

    revised_blocks: list[str] = []
    for block in blocks:
        revised = revise_markdown_block(
            block_text=block,
            assist_texts=assist_texts,
            model=model,
            base_url=base_url,
            timeout=timeout,
            cli_path=cli_path,
        )
        revised_blocks.append(revised.strip())

    return "\n\n".join(b for b in revised_blocks if b).strip()


def concatenate_pages(page_parts: list[str]) -> str:
    text = "\n\n".join(part.strip() for part in page_parts if part.strip()).strip()
    return text + ("\n" if text else "")


def main() -> int:
    args = parse_args()
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    format_block_content = args.format_block_content
    use_assist = not args.no_assist

    inputs = discover_inputs(args.inputs)
    output_dir = args.output_dir.resolve()
    pages_dir = output_dir / f"{args.name}_pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    selected_engine = args.engine
    pipeline = build_pipeline(selected_engine, args.lang, format_block_content, args.pipeline_version)
    assist_ocrs = build_assist_ocrs(use_assist)

    if args.lmstudio_transport == "cli":
        cli_path = args.lmstudio_cli or find_default_lms()
        if cli_path is None:
            raise FileNotFoundError("LM Studio CLI requested, but no lms executable was found.")
    else:
        cli_path = None

    book_raw_parts: list[str] = []
    book_final_parts: list[str] = []
    book_jsonl_rows: list[str] = []

    with tempfile.TemporaryDirectory(prefix="book_digitize_") as temp_dir_raw:
        temp_root = Path(temp_dir_raw)

        prepared_pages = prepare_input_pages(
            inputs=inputs,
            temp_root=temp_root,
            dpi=args.dpi,
            max_pages=args.max_pages,
        )

        if not prepared_pages:
            raise RuntimeError("No pages prepared for OCR.")

        for page_info in prepared_pages:
            page_number = page_info["page_number"]
            source_file: Path = page_info["source_file"]
            source_page_index: int = page_info["source_page_index"]
            input_path: Path = page_info["input_path"]

            try:
                result = run_pipeline_on_page(
                    pipeline=pipeline,
                    engine=selected_engine,
                    format_block_content=format_block_content,
                    page_path=input_path,
                )
            except Exception as exc:
                if selected_engine == "ocrvl" and args.fallback_engine == "ppstructure":
                    print(
                        f"OCR engine 'ocrvl' failed on page {page_number} with {exc}. Falling back to 'ppstructure'.",
                        file=sys.stderr,
                    )
                    selected_engine = "ppstructure"
                    pipeline = build_pipeline(
                        selected_engine,
                        args.lang,
                        format_block_content,
                        args.pipeline_version,
                    )
                    result = run_pipeline_on_page(
                        pipeline=pipeline,
                        engine=selected_engine,
                        format_block_content=format_block_content,
                        page_path=input_path,
                    )
                else:
                    raise

            markdown_text = extract_markdown_text(result)
            page_header = format_page_header(page_number, source_file, source_page_index)

            raw_page_markdown = f"{page_header}\n\n{markdown_text}\n"
            page_stem = f"page_{page_number:04d}"

            write_text(pages_dir / f"{page_stem}.raw.md", raw_page_markdown)
            book_raw_parts.append(raw_page_markdown.strip())

            json_payload = getattr(result, "json", None) or {}
            assist_texts: dict[str, str] = {}

            if use_assist:
                assist_texts = extract_assist_texts(assist_ocrs, input_path)
                for lang, assist_text in assist_texts.items():
                    write_text(pages_dir / f"{page_stem}.assist_{lang}.txt", assist_text + "\n")

            final_body = markdown_text
            if args.revise:
                final_body = revise_markdown_text(
                    text=markdown_text,
                    assist_texts=assist_texts,
                    model=args.lmstudio_model,
                    base_url=args.lmstudio_base_url,
                    timeout=args.timeout,
                    cli_path=cli_path,
                    chunk_size=args.chunk_size,
                )

            final_page_markdown = f"{page_header}\n\n{final_body}\n"
            write_text(pages_dir / f"{page_stem}.final.md", final_page_markdown)
            book_final_parts.append(final_page_markdown.strip())

            payload = {
                "page_number": page_number,
                "source_file": str(source_file),
                "source_page_index": source_page_index,
                "preprocessed_input": str(input_path),
                "engine": selected_engine,
                "requested_engine": args.engine,
                "lang": args.lang,
                "assist_langs": list(assist_texts.keys()),
                "markdown_text_raw": markdown_text,
                "markdown_text_final": final_body,
                "result": json_payload,
            }
            write_text(
                pages_dir / f"{page_stem}.json",
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            book_jsonl_rows.append(json.dumps(payload, ensure_ascii=False))

            print(f"Processed page {page_number}: {source_file.name} [src_page={source_page_index}]")

        raw_markdown = concatenate_pages(book_raw_parts)
        final_markdown = concatenate_pages(book_final_parts)
        raw_markdown_path = output_dir / f"{args.name}.raw.md"
        final_markdown_path = output_dir / f"{args.name}.md"
        jsonl_path = output_dir / f"{args.name}.jsonl"

        write_text(raw_markdown_path, raw_markdown)
        write_text(final_markdown_path, final_markdown)
        write_text(jsonl_path, "\n".join(book_jsonl_rows) + ("\n" if book_jsonl_rows else ""))

        print(f"Raw Markdown: {raw_markdown_path}")
        print(f"Final Markdown: {final_markdown_path}")
        print(f"JSONL: {jsonl_path}")
        print(f"Per-page outputs: {pages_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
