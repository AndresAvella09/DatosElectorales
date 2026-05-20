# cargar_parlamentarias.ps1
# Carga todos los CSV de data\parlamentarias\ a Supabase en las tablas
# raw.posts_parlamentarias y silver.posts_parlamentarias.
#
# Pipeline identico al de elecciones presidenciales:
#   Bronze (raw.posts_parlamentarias) -> Silver (silver.posts_parlamentarias)
# No pasa por Gold (dataset historico fijo, no requiere agregados gold).
#
# Uso:
#   .\scripts\cargar_parlamentarias.ps1
#   .\scripts\cargar_parlamentarias.ps1 -SoloFuente tiktok
#   .\scripts\cargar_parlamentarias.ps1 -SubirStorage
#
# Requiere: uv instalado, .env con SUPABASE_URL y SUPABASE_KEY en la raiz.

param(
    [string]$SoloFuente  = "",    # Corre solo una fuente si se especifica
    [switch]$SubirStorage         # Guarda el CSV crudo en bucket bronze-raw
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$base = Join-Path $root "data\parlamentarias"

# Columna fuente -> nombre de archivo exacto en data\parlamentarias\
$archivos = @(
    @{ fuente = "facebook"; csv = Join-Path $base "facebook_parlamentarias_antes.csv" },
    @{ fuente = "facebook"; csv = Join-Path $base "facebook_parlamentarias_despues.csv" },
    @{ fuente = "tiktok";   csv = Join-Path $base "tiktok_comments_parlamentarias (1).csv" },
    @{ fuente = "twitter";  csv = Join-Path $base "tweets_parlamentarias_reordered.csv" },
    @{ fuente = "youtube";  csv = Join-Path $base "youtube_parlamentarias_comments.csv" }
)

# ── Helpers ────────────────────────────────────────────────────────
function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "    ERR $msg" -ForegroundColor Red }

# ── Validar archivos antes de empezar ─────────────────────────────
Write-Step "Verificando archivos en data\parlamentarias\..."
$faltantes = 0
foreach ($item in $archivos) {
    if ($SoloFuente -and $item.fuente -ne $SoloFuente) { continue }
    if (-not (Test-Path $item.csv)) {
        Write-Err "No encontrado: $($item.csv)"
        $faltantes++
    } else {
        Write-Ok "$($item.fuente): $(Split-Path $item.csv -Leaf)"
    }
}
if ($faltantes -gt 0) {
    Write-Host "`nFaltan $faltantes archivo(s). Abortando." -ForegroundColor Red
    exit 1
}

$storageFlag = if ($SubirStorage) { "--upload-to-storage" } else { "" }

# ── Correr e2e por cada CSV ────────────────────────────────────────
$ok  = 0
$err = 0

foreach ($item in $archivos) {
    if ($SoloFuente -and $item.fuente -ne $SoloFuente) { continue }

    $nombre = Split-Path $item.csv -Leaf
    Write-Step "[$($item.fuente.ToUpper())] $nombre"

    $cmd = @(
        "run", "python", "-m", "data_pipeline.loaders.cli",
        "e2e",
        "--csv",    $item.csv,
        "--source", $item.fuente,
        "--table",  "posts_parlamentarias",
        "--no-archive"
    )
    if ($storageFlag) { $cmd += $storageFlag }

    Write-Host "    $ uv $($cmd -join ' ')" -ForegroundColor DarkGray

    Push-Location $root
    try {
        & uv @cmd
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Completado"
            $ok++
        } else {
            Write-Err "Salio con codigo $LASTEXITCODE"
            $err++
        }
    } catch {
        Write-Err $_.Exception.Message
        $err++
    } finally {
        Pop-Location
    }
}

# ── Resumen ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "─────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  CSVs OK  : $ok  -> raw.posts_parlamentarias + silver.posts_parlamentarias" -ForegroundColor Green
if ($err -gt 0) {
    Write-Host "  CSVs ERR : $err" -ForegroundColor Red
    exit 1
}
