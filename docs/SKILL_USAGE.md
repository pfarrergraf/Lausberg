# Using the Repo Skill

This repo includes a reusable skill at:

- `skills/lausberg-workbench/SKILL.md`

The skill documents the working OCR defaults and the `Stilmittel.json` maintenance rules for this project.

## Using it from Codex

Two practical options:

1. Repo-local use

Ask Codex to read and follow:

```text
Use the repo skill at skills/lausberg-workbench/SKILL.md
```

2. Install it as a named Codex skill

Copy or symlink `skills/lausberg-workbench/` into your Codex skills directory so it becomes available by name in future sessions.

Typical location:

```text
$CODEX_HOME/skills/lausberg-workbench/
```

## Using it from GitHub Copilot

Copilot can read repo files directly. The easiest pattern is:

- keep `.github/copilot-instructions.md` in the repo
- mention `skills/lausberg-workbench/SKILL.md` in your prompt when you want the OCR or Stilmittel workflow applied

Example prompt:

```text
Use the repo guidance in .github/copilot-instructions.md and the workflow in skills/lausberg-workbench/SKILL.md. Update the OCR pipeline without changing the Stilmittel schema.
```

## What the skill covers

- local OCR defaults for JPG and PDF work
- when to use Surya vs Tesseract
- where to compare outputs
- how to treat `Stilmittel.json` and `SYSTEM_PROMPT_Stilmittel_Generator.md`

## What it does not do

- It does not auto-install Python packages
- It does not auto-run OCR jobs
- It does not replace repo-specific prompt context in the current chat unless the tool or user explicitly points the agent to it
