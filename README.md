# Lausberg Workbench

This repo is a Windows-first workbench for two related tasks:

- local OCR and digitization of the Lausberg PDFs and JPG page exports
- structured rhetoric dataset work around `Stilmittel.json`

The currently preferred local OCR path is `Surya` in `.venv`, plus post-processing in `scripts/ocr_pipeline.py`. For clean single-image pages, Docker Tesseract is still a useful baseline. For mixed-language PDFs, Surya is the default local choice.

## Repo layout

- `scripts/`: OCR runners, comparisons, and helper tools
- `output/`: OCR runs, evaluations, and intermediate artifacts
- `pdf/`: PDF-side helper assets
- `Seiten jpg/`: page image inputs
- `Stilmittel.json`: rhetoric dataset
- `SYSTEM_PROMPT_Stilmittel_Generator.md`: schema and tone rules for Stilmittel generation

## Environments

- `.venv`: active local OCR environment for Surya and OCR cleanup
- `.venv-paddleocr`: legacy PaddleOCR comparison environment

Use `uv`, not `pip`, for package changes.

## Local OCR workflow

Recommended flow:

1. Start with one JPG or a 5-page PDF slice.
2. Compare the result to older outputs in `output/ocr_eval/`.
3. Only then run larger PDFs.

Single image:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\surya_local_ocr.ps1 -InputPath "output\ocr_eval\prep\20260318_171511_preprocessed_rot-90.png" -OutputDir "output\ocr_eval\surya_local_jpg" -DisableMath
```

5-page PDF with local LM Studio cleanup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\surya_local_ocr.ps1 -InputPath "output\ocr_eval\pdf5\kapitel_i_first5.pdf" -OutputDir "output\ocr_eval\surya_local_pdf5_lm" -DisableMath -ReviseWithLmStudio -LmStudioModel "qwen2.5-32b-instruct" -TimeoutSeconds 600
```

Key OCR files:

- `scripts/surya_local_ocr.ps1`
- `scripts/ocr_pipeline.py`
- `scripts/tesseract_docker_ocr.ps1`
- `scripts/tesseract_docker_batch.ps1`

## Stilmittel workflow

`Stilmittel.json` is not free-form content. Preserve the existing schema, German field names, and rhetorical/theological register defined in `SYSTEM_PROMPT_Stilmittel_Generator.md`.

When extending the dataset:

- keep JSON valid and schema-stable
- do not duplicate existing entries unless asked
- preserve Greek and Latin source terms when present
- prefer distinct, high-signal examples over generic filler

## Repo guidance

- Repo-specific agent instructions: `AGENTS.md`
- GitHub Copilot guidance: `.github/copilot-instructions.md`
- Repo skill: `skills/lausberg-workbench/SKILL.md`
- Skill usage note: `docs/SKILL_USAGE.md`
