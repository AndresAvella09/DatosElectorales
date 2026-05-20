# ---------------------------------------------------------------------
# scripts/scrape_youtube.ps1
#
# Corre el scraper de YouTube (local, usa YOUTUBE_API_KEY* del .env).
# Deja los CSV en data/inbox/youtube/<YYYY-MM-DD>/run_<HHMMSS>_*.csv.
#
# Si el stack DataOps esta arriba (.\scripts\start.ps1), el watcher en
# Docker detecta los CSV automaticamente y dispara pipeline_e2e.
# Si no, los archivos quedan en inbox/ esperando.
#
# Las queries (palabras clave) y los caps de paginacion estan en
# packages/scrapers/youtube/youtube.py (YOUTUBE_QUERIES, YOUTUBE_MAX_*).
# Editar ahi si necesitas cambiarlos.
#
# Uso:
#     .\scripts\scrape_youtube.ps1
# ---------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path ".env")) {
    Write-Host "ERROR: falta .env en la raiz del repo (necesita YOUTUBE_API_KEY)." -ForegroundColor Red
    exit 1
}

Write-Host "[scrape_youtube] arrancando..." -ForegroundColor Cyan
uv run python packages/scrapers/youtube/youtube.py
$exit = $LASTEXITCODE

if ($exit -eq 0) {
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $outDir = Join-Path $repoRoot "data\inbox\youtube\$today"
    Write-Host ""
    Write-Host "[OK] Scraper YouTube terminado." -ForegroundColor Green
    if (Test-Path $outDir) {
        Write-Host "CSVs en $outDir :"
        Get-ChildItem $outDir -Filter "*.csv" | Select-Object Name, Length, LastWriteTime | Format-Table
    }
    Write-Host "Si el stack esta arriba, mira el FlowRun en http://localhost:4200"
}

exit $exit
