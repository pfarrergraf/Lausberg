param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [string]$OutputDir = "output\\tesseract_docker",

    [string]$Langs = "deu+lat+grc+fra+eng",

    [int]$Psm = 1,

    [int]$RotateDegrees = 0,

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
    param(
        [int]$TimeoutSeconds = 120
    )

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
    param(
        [string]$LangList
    )

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
                throw "Unsupported language token '$lang'. Add a package mapping in scripts\\tesseract_docker_ocr.ps1 first."
            }
        }
    }

    return $packages | Select-Object -Unique
}

$repoRoot = Get-RepoRoot
$resolvedInput = (Resolve-Path (Resolve-RepoPath -Path $InputPath -RepoRoot $repoRoot)).Path
$resolvedOutputDir = Resolve-RepoPath -Path $OutputDir -RepoRoot $repoRoot

New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null
$tempDir = Join-Path $resolvedOutputDir "_prepared"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

$preparedExt = [System.IO.Path]::GetExtension($resolvedInput)
if (-not $preparedExt) {
    $preparedExt = ".png"
}

$preparedPath = Join-Path $tempDir ("{0}{1}" -f [System.IO.Path]::GetFileNameWithoutExtension($resolvedInput), $preparedExt)
if ($RotateDegrees -ne 0) {
    magick $resolvedInput -rotate $RotateDegrees $preparedPath
}
else {
    Copy-Item -Force $resolvedInput $preparedPath
}

Ensure-DockerReady

$packages = Get-TesseractPackages -LangList $Langs
$repoMount = ($repoRoot -replace "\\", "/")
$preparedRelative = (Get-RelativePathCompat -BasePath $repoRoot -TargetPath $preparedPath) -replace "\\", "/"
$outputBase = Join-Path $resolvedOutputDir ([System.IO.Path]::GetFileNameWithoutExtension($preparedPath))
$outputBaseRelative = (Get-RelativePathCompat -BasePath $repoRoot -TargetPath $outputBase) -replace "\\", "/"

$aptPackages = $packages -join " "
$bashTemplate = @'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update >/tmp/apt-update.log
apt-get install -y --no-install-recommends {0} >/tmp/apt-install.log
start=$(date +%s%3N)
tesseract '/work/{1}' '/work/{2}' -l '{3}' --psm {4} > '/work/{2}.stderr.txt' 2>&1
end=$(date +%s%3N)
echo "elapsed_ms=$((end-start))" > '/work/{2}.time.txt'
'@

$bashScript = [string]::Format(
    $bashTemplate,
    $aptPackages,
    $preparedRelative,
    $outputBaseRelative,
    $Langs,
    $Psm
)

docker run --rm -v "${repoMount}:/work" $DockerImage bash -lc $bashScript

Write-Host "Prepared input: $preparedPath"
Write-Host "OCR text: $outputBase.txt"
Write-Host "OCR stderr: $outputBase.stderr.txt"
Write-Host "Runtime: $outputBase.time.txt"
