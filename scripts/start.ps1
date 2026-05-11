# ---------------------------------------------------------------------
# scripts/start.ps1
#
# Levanta el stack DataOps completo (Prefect + watcher + API) y deja
# todo listo para que cualquier CSV que aparezca en data/inbox/<source>/
# sea procesado automaticamente y visible en la UI de Prefect.
#
# Uso:
#     .\scripts\start.ps1            # arranca todo en background
#     .\scripts\start.ps1 -Logs      # arranca y hace tail de logs
#     .\scripts\start.ps1 -Down      # apaga el stack
#     .\scripts\start.ps1 -Rebuild   # rebuild imagenes y arrancar
#
# Requisitos: Docker Desktop corriendo, .env en la raiz del repo.
# ---------------------------------------------------------------------

param(
    [switch]$Logs,
    [switch]$Down,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$compose  = Join-Path $repoRoot "infra\docker-compose.yml"

if (-not (Test-Path (Join-Path $repoRoot ".env"))) {
    Write-Host "WARN: no se encontro .env en la raiz del repo." -ForegroundColor Yellow
    Write-Host "      Copia .env.example a .env y completa SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY." -ForegroundColor Yellow
}

# Crear carpetas mapeadas para que docker no las cree como root.
New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot "data\inbox") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot "data\processed") | Out-Null

if ($Down) {
    Write-Host "Deteniendo stack..." -ForegroundColor Cyan
    docker compose -f $compose down
    exit $LASTEXITCODE
}

$buildFlag = if ($Rebuild) { "--build" } else { "" }

Write-Host "Levantando stack DataOps..." -ForegroundColor Cyan
docker compose -f $compose up -d $buildFlag
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[OK] Stack arriba." -ForegroundColor Green
Write-Host ""
Write-Host "  Prefect UI : http://localhost:4200" -ForegroundColor White
Write-Host "  API        : http://localhost:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "El watcher esta observando data/inbox/<source>/<YYYY-MM-DD>/*.csv."
Write-Host "Cuando llegue un CSV se vera un FlowRun en Prefect con el grafo:"
Write-Host "  bronze.load_csv -> bronze_to_silver -> quality_gate"
Write-Host ""
Write-Host "Comandos utiles:"
Write-Host "  .\scripts\start.ps1 -Logs      # tail de logs"
Write-Host "  .\scripts\start.ps1 -Down      # apagar"
Write-Host "  .\scripts\start.ps1 -Rebuild   # rebuild imagenes y arrancar"
Write-Host ""

if ($Logs) {
    docker compose -f $compose logs -f worker prefect
}
