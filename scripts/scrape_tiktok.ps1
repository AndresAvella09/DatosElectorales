# ---------------------------------------------------------------------
# scripts/scrape_tiktok.ps1
#
# Corre el scraper de TikTok (local, lee msToken de cookies del browser).
# Deja los CSV en data/inbox/tiktok/<YYYY-MM-DD>/run_<HHMMSS>_*.csv.
#
# Si el stack DataOps esta arriba (.\scripts\start.ps1), el watcher en
# Docker detecta los CSV automaticamente y dispara pipeline_e2e.
#
# Uso:
#     .\scripts\scrape_tiktok.ps1
#     .\scripts\scrape_tiktok.ps1 eleccionescolombia2026
#     .\scripts\scrape_tiktok.ps1 eleccionescolombia2026 60
#
# Args:
#     args[0]  HASHTAG       (override de env)
#     args[1]  VIDEO_COUNT   (override de env)
# Si se omiten, usa los valores del .env.
#
# Primera vez:  uv run playwright install chromium
# ---------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path ".env")) {
    Write-Host "ERROR: falta .env en la raiz del repo." -ForegroundColor Red
    exit 1
}

if ($args[0]) { $env:HASHTAG     = $args[0] }
if ($args[1]) { $env:VIDEO_COUNT = $args[1] }

Write-Host "[scrape_tiktok] arrancando (hashtag=$env:HASHTAG count=$env:VIDEO_COUNT)..." -ForegroundColor Cyan
uv run python -m packages.scrapers.tiktok.scrape_tiktok
$exit = $LASTEXITCODE

if ($exit -eq 0) {
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $outDir = Join-Path $repoRoot "data\inbox\tiktok\$today"
    Write-Host ""
    Write-Host "[OK] Scraper TikTok terminado." -ForegroundColor Green
    if (Test-Path $outDir) {
        Write-Host "CSVs en $outDir :"
        Get-ChildItem $outDir -Filter "*.csv" | Select-Object Name, Length, LastWriteTime | Format-Table
    }
    Write-Host "Si el stack esta arriba, mira el FlowRun en http://localhost:4200"
}

exit $exit
