param(
    [Parameter(Mandatory = $true)]
    [string]$InputDir,

    [string]$OutputDir = "output\\tesseract_docker_batch",

    [string]$Langs = "deu+lat+grc+fra+eng",

    [int]$Psm = 1,

    [string]$Filter = "*.png",

    [string]$DockerImage = "ubuntu:24.04"
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Resolve-RepoPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Path))
}

function Get-RelativePathCompat {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,

        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $baseFull = [System.IO.Path]::GetFullPath($BasePath)
    $targetFull = [System.IO.Path]::GetFullPath($TargetPath)
    if (-not $baseFull.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $baseFull += [System.IO.Path]::DirectorySeparatorChar
    }

    $baseUri = [System.Uri]::new($baseFull)
    $targetUri = [System.Uri]::new($targetFull)
    $relativeUri = $baseUri.MakeRelativeUri($targetUri)
    return [System.Uri]::UnescapeDataString($relativeUri.ToString()).Replace("/", "\")
}

function Wait-DockerReady {
    param([int]$TimeoutSeconds = 120)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = docker info --format "{{.OSType}}" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return
            }
        }
        catch {
        }
        Start-Sleep -Seconds 5
    }

    throw "Docker engine did not become ready within $TimeoutSeconds seconds."
}

function Ensure-DockerReady {
    try {
        $null = docker info --format "{{.OSType}}" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return
        }
    }
    catch {
    }

    $desktopPath = "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"
    if (Test-Path $desktopPath) {
        Start-Process $desktopPath | Out-Null
        Wait-DockerReady
        return
    }

    throw "Docker is not ready and Docker Desktop was not found."
}

function Get-TesseractPackages {
    param([string]$LangList)

    $packages = [System.Collections.Generic.List[string]]::new()
    $packages.Add("tesseract-ocr")

    foreach ($lang in ($LangList -split "\+")) {
        switch ($lang.Trim()) {
            "deu" { $packages.Add("tesseract-ocr-deu") }
            "eng" { $packages.Add("tesseract-ocr-eng") }
            "fra" { $packages.Add("tesseract-ocr-fra") }
            "grc" { $packages.Add("tesseract-ocr-grc") }
            "lat" { $packages.Add("tesseract-ocr-lat") }
            "script/Latin" { $packages.Add("tesseract-ocr-script-latn") }
            default {
                throw "Unsupported language token '$lang'. Add a package mapping in scripts\\tesseract_docker_batch.ps1 first."
            }
        }
    }

    return $packages | Select-Object -Unique
}

$repoRoot = Get-RepoRoot
$resolvedInputDir = (Resolve-Path (Resolve-RepoPath -Path $InputDir -RepoRoot $repoRoot)).Path
$resolvedOutputDir = Resolve-RepoPath -Path $OutputDir -RepoRoot $repoRoot

New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

$inputFiles = Get-ChildItem -Path $resolvedInputDir -File -Filter $Filter | Sort-Object Name
if (-not $inputFiles) {
    throw "No files matched '$Filter' in '$resolvedInputDir'."
}

Ensure-DockerReady

$packages = Get-TesseractPackages -LangList $Langs
$aptPackages = $packages -join " "
$repoMount = ($repoRoot -replace "\\", "/")

$commands = [System.Collections.Generic.List[string]]::new()
$commands.Add("set -e")
$commands.Add("export DEBIAN_FRONTEND=noninteractive")
$commands.Add("apt-get update >/tmp/apt-update.log")
$commands.Add("apt-get install -y --no-install-recommends $aptPackages >/tmp/apt-install.log")

foreach ($file in $inputFiles) {
    $inputRelative = (Get-RelativePathCompat -BasePath $repoRoot -TargetPath $file.FullName) -replace "\\", "/"
    $outputBase = Join-Path $resolvedOutputDir $file.BaseName
    $outputRelative = (Get-RelativePathCompat -BasePath $repoRoot -TargetPath $outputBase) -replace "\\", "/"
    $commands.Add("start=`$(date +%s%3N)")
    $commands.Add("tesseract '/work/$inputRelative' '/work/$outputRelative' -l '$Langs' --psm $Psm > '/work/$outputRelative.stderr.txt' 2>&1")
    $commands.Add("end=`$(date +%s%3N)")
    $commands.Add("echo ""elapsed_ms=`$((end-start))"" > '/work/$outputRelative.time.txt'")
}

$bashScript = ($commands -join "`n")
docker run --rm -v "${repoMount}:/work" $DockerImage bash -lc $bashScript

Write-Host "Input files: $($inputFiles.Count)"
Write-Host "OCR outputs: $resolvedOutputDir"
