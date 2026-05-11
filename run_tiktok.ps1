# Usage: .\run_tiktok.ps1 [HASHTAG] [VIDEO_COUNT]
# Example: .\run_tiktok.ps1 eleccionescolombia2026 60
# Falls back to .env values when args are omitted.

$ErrorActionPreference = "Stop"
$Tiktok = "$PSScriptRoot\data_pipeline\ingestion\tiktok"
$Venv   = "$Tiktok\venv"
$Python = "$Venv\Scripts\python.exe"
$Pip    = "$Venv\Scripts\pip.exe"
$PW     = "$Venv\Scripts\playwright.exe"

if ($args[0]) { $env:HASHTAG     = $args[0] }
if ($args[1]) { $env:VIDEO_COUNT = $args[1] }

# Create venv if missing
if (-not (Test-Path $Python)) {
    Write-Host "[setup] Creating virtual environment..."
    python -m venv $Venv
}

# Install requirements
Write-Host "[setup] Installing requirements..."
& $Pip install -q -r "$Tiktok\requirements.txt"

# Install local TikTokApi package
Push-Location $Tiktok
& $Pip install -q -e .
Pop-Location

# Install Playwright browser if needed
Write-Host "[setup] Checking Playwright browser..."
& $PW install chromium --with-deps 2>$null

# Run the scraper
Write-Host "[run] Starting scraper..."
& $Python "$Tiktok\examples\scrape_hashtag_comments.py"
