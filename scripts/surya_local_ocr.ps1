param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [string]$OutputDir = "output\ocr_local",

    [string]$TaskName = "ocr_without_boxes",

    [string]$DocumentKey = "",

    [switch]$DisableMath,

    [switch]$ReviseWithLmStudio,

    [string]$LmStudioModel = "qwen2.5-32b-instruct",

    [int]$TimeoutSeconds = 600
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$suryaExe = Join-Path $repoRoot ".venv\Scripts\surya_ocr.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Missing Python venv executable: $pythonExe"
}

if (-not (Test-Path $suryaExe)) {
    throw "Missing Surya CLI executable: $suryaExe"
}

$resolvedInput = (Resolve-Path $InputPath).Path
$resolvedOutputDir = if ([System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir
} else {
    Join-Path $repoRoot $OutputDir
}

New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

if ([string]::IsNullOrWhiteSpace($DocumentKey)) {
    $DocumentKey = [System.IO.Path]::GetFileNameWithoutExtension($resolvedInput)
}

$suryaArgs = @(
    $resolvedInput
    "--output_dir"
    $resolvedOutputDir
    "--debug"
    "--task_name"
    $TaskName
)

if ($DisableMath.IsPresent) {
    $suryaArgs += "--disable_math"
}

& $suryaExe @suryaArgs
if ($LASTEXITCODE -ne 0) {
    throw "surya_ocr failed with exit code $LASTEXITCODE"
}

$documentDir = Join-Path $resolvedOutputDir $DocumentKey
$resultsPath = Join-Path $documentDir "results.json"
$rawOutputPath = Join-Path $documentDir "ordered_raw.txt"

if (-not (Test-Path $resultsPath)) {
    throw "Expected Surya results at $resultsPath"
}

$pipelineArgs = @(
    "scripts\ocr_pipeline.py"
    "--results"
    $resultsPath
    "--raw-output"
    $rawOutputPath
    "--document-key"
    $DocumentKey
)

if ($ReviseWithLmStudio.IsPresent) {
    $revisedOutputPath = Join-Path $documentDir "ordered_revised.txt"
    $pipelineArgs += @(
        "--revise-output"
        $revisedOutputPath
        "--lmstudio-model"
        $LmStudioModel
        "--timeout"
        $TimeoutSeconds
    )
}

Push-Location $repoRoot
try {
    & $pythonExe @pipelineArgs
    if ($LASTEXITCODE -ne 0) {
        throw "ocr_pipeline.py failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Results JSON : $resultsPath"
Write-Host "Raw text     : $rawOutputPath"
if ($ReviseWithLmStudio.IsPresent) {
    Write-Host "Revised text : $revisedOutputPath"
}
