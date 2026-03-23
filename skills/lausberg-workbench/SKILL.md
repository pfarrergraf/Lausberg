---
name: "lausberg-workbench"
description: "Use when working in this repo on Lausberg OCR runs, OCR comparisons, or Stilmittel.json maintenance."
---

# Lausberg Workbench

## When to use

- Run or debug local OCR on Lausberg PDFs or JPG page images
- Compare Surya, Tesseract, Paddle, or prior OCR outputs
- Update `Stilmittel.json`
- Update the Lausberg prompt or dataset-generation guidance

## Default choices

- Preferred local PDF OCR path: `scripts/surya_local_ocr.ps1`
- OCR cleanup and ordering: `scripts/ocr_pipeline.py`
- Clean JPG baseline: Docker Tesseract
- Main OCR env: `.venv`
- Legacy Paddle comparison env: `.venv-paddleocr`

## OCR workflow

1. Start small.
   Use one JPG or a 5-page PDF slice before any large run.
2. Keep comparisons grounded.
   Compare new output against older files in `output/ocr_eval/`.
3. Prefer the local Surya path first.
   Use LM Studio cleanup only when the raw output still has duplicated fragments or mixed-script noise.
4. Do not spend cloud OCR credits unless the user explicitly wants that tradeoff.

## Canonical commands

Single image:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\surya_local_ocr.ps1 -InputPath "output\ocr_eval\prep\20260318_171511_preprocessed_rot-90.png" -OutputDir "output\ocr_eval\surya_local_jpg" -DisableMath
```

5-page PDF with local cleanup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\surya_local_ocr.ps1 -InputPath "output\ocr_eval\pdf5\kapitel_i_first5.pdf" -OutputDir "output\ocr_eval\surya_local_pdf5_lm" -DisableMath -ReviseWithLmStudio -LmStudioModel "qwen2.5-32b-instruct" -TimeoutSeconds 600
```

Tesseract JPG comparison:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\tesseract_docker_ocr.ps1 -InputPath "Seiten jpg\20260318_171511.jpg" -OutputDir "output\ocr_eval\tesseract_wrapper" -Langs "deu+lat+grc+fra+eng" -RotateDegrees -90
```

## OCR outputs to inspect

- `results.json`
- `ordered_raw.txt`
- `ordered_revised.txt`

Prefer storing new experiment results under a descriptive output folder rather than overwriting older runs.

## Stilmittel workflow

- Preserve the JSON schema in `Stilmittel.json`
- Follow the tone and structure rules in `SYSTEM_PROMPT_Stilmittel_Generator.md`
- Keep Greek and Latin source terms intact when known
- Avoid duplicates unless the task is explicitly to merge or revise an existing entry

## Key files

- `scripts/surya_local_ocr.ps1`
- `scripts/ocr_pipeline.py`
- `scripts/tesseract_docker_ocr.ps1`
- `scripts/tesseract_docker_batch.ps1`
- `Stilmittel.json`
- `SYSTEM_PROMPT_Stilmittel_Generator.md`
