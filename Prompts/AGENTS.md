# AGENTS.md

## Scope

This repo has two main responsibilities:

- OCR and digitization experiments for Lausberg PDFs and page images
- maintenance and extension of `Stilmittel.json` plus related prompt files

## Working defaults

- Use Windows PowerShell commands unless there is a clear reason to switch.
- Use `.venv` for Surya OCR work.
- Use `.venv-paddleocr` only for legacy PaddleOCR comparisons.
- Use `uv` for package management.
- Treat large OCR runs as expensive. Start with one JPG or a 5-page PDF slice first.
- Always compare a new OCR result against an older result in `output/ocr_eval/` when possible.

## OCR rules

- Preferred local PDF path: `scripts/surya_local_ocr.ps1` plus `scripts/ocr_pipeline.py`
- Best local clean-image baseline: Docker Tesseract
- Use DocuPipe only when the user explicitly accepts cloud credits or when local results are clearly insufficient
- For LM Studio cleanup, default to `qwen2.5-32b-instruct`
- Put new OCR experiments under descriptive subfolders in `output/ocr_eval/` or `output/`
- Avoid overwriting prior comparison outputs unless the user asks for replacement

## OCR files to know

- `scripts/surya_local_ocr.ps1`
- `scripts/ocr_pipeline.py`
- `scripts/tesseract_docker_ocr.ps1`
- `scripts/tesseract_docker_batch.ps1`
- `scripts/docupipe_ocr_eval.py`

## Stilmittel rules

- Preserve the schema and register defined in `SYSTEM_PROMPT_Stilmittel_Generator.md`
- Keep `Stilmittel.json` valid JSON
- Do not rename fields or change field casing without an explicit migration task
- Preserve Greek and Latin terms exactly when known
- Prefer precise rhetoric terminology over paraphrase
- Avoid duplicate entries unless the task is deduplication or consolidation

## Output expectations

- For OCR work, report which engine or pipeline won and why
- For Stilmittel work, name the affected entry or concept and keep schema changes explicit
- For benchmark work, include the sample used and whether it was JPG, PDF slice, or full PDF
