# Copilot Instructions

This repo is a Lausberg OCR and rhetoric workbench. Keep suggestions grounded in the actual local workflow already present here.

## Environment

- Windows-first repo
- Prefer PowerShell command examples
- Use `uv` for Python package changes
- Main OCR env: `.venv`
- Legacy Paddle env: `.venv-paddleocr`

## OCR guidance

- Default local OCR path: `scripts/surya_local_ocr.ps1`
- OCR cleanup and ordering live in `scripts/ocr_pipeline.py`
- Use Docker Tesseract only as a comparison baseline or for clean single-image runs
- Before suggesting a large OCR run, suggest a single JPG or a 5-page PDF slice first
- When proposing OCR changes, compare against existing outputs under `output/ocr_eval/`

## Stilmittel guidance

- `Stilmittel.json` must stay schema-compatible
- Follow `SYSTEM_PROMPT_Stilmittel_Generator.md`
- Preserve Greek and Latin terminology
- Prefer precise rhetoric terms, not generic stylistics language

## Editing style

- Keep repo docs practical and command-oriented
- Do not introduce new package workflows when `uv` is sufficient
- Do not suggest CPU fallback by default for OCR/model tasks
