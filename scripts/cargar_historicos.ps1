# cargar_historicos.ps1
# Abre un selector de archivo, detecta la fuente automaticamente y corre
# el pipeline completo: Bronze -> Silver -> Gold con deduplicacion.
#
# Uso interactivo (abre dialogo):
#   .\scripts\cargar_historicos.ps1
#
# Uso con argumentos (sin dialogo):
#   .\scripts\cargar_historicos.ps1 -Csv "ruta\al\archivo.csv" -Fuente tiktok
#   .\scripts\cargar_historicos.ps1 -SubirStorage
#
# Requiere: uv instalado, .env con SUPABASE_URL y SUPABASE_KEY en la raiz.

param(
    [string]$Csv      = "",     # Ruta al CSV. Si no se pasa, abre el selector.
    [string]$Fuente   = "",     # facebook|tiktok|youtube|twitter. Si no se pasa, se autodetecta.
    [switch]$SubirStorage       # Guarda el CSV crudo en el bucket bronze-raw (off por default).
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

# ── Helpers ────────────────────────────────────────────────────────
function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "    ERR $msg" -ForegroundColor Red }
function Write-Info($msg) { Write-Host "    ... $msg" -ForegroundColor DarkGray }

# ── Selector de archivo (dialogo Windows) ─────────────────────────
function Select-Csv {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title  = "Selecciona el CSV a subir al pipeline"
    $dialog.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
    $dialog.InitialDirectory = $root

    $result = $dialog.ShowDialog()
    if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host "Cancelado." -ForegroundColor Yellow
        exit 0
    }
    return $dialog.FileName
}

# ── Autodetectar fuente desde el nombre del archivo ────────────────
$fuentePatrones = @{
    "facebook" = @("facebook", "fb_")
    "tiktok"   = @("tiktok", "tk_")
    "youtube"  = @("youtube", "yt_")
    "twitter"  = @("tweet", "twitter", "tw_")
}

function Detect-Fuente([string]$nombreArchivo) {
    $lower = $nombreArchivo.ToLower()
    foreach ($fuente in $fuentePatrones.Keys) {
        foreach ($patron in $fuentePatrones[$fuente]) {
            if ($lower -contains $patron -or $lower.IndexOf($patron) -ge 0) {
                return $fuente
            }
        }
    }
    return $null
}

# ── Elegir fuente interactivamente si no se detecta ───────────────
function Ask-Fuente([string]$nombreArchivo) {
    Write-Host "`n  No se pudo detectar la fuente desde el nombre: '$nombreArchivo'" -ForegroundColor Yellow
    Write-Host "  Elige la fuente:"
    $opciones = @("facebook", "tiktok", "youtube", "twitter")
    for ($i = 0; $i -lt $opciones.Count; $i++) {
        Write-Host "    [$($i+1)] $($opciones[$i])"
    }
    do {
        $sel = Read-Host "  Opcion (1-4)"
        $idx = [int]$sel - 1
    } while ($idx -lt 0 -or $idx -ge $opciones.Count)
    return $opciones[$idx]
}

# ── Main ───────────────────────────────────────────────────────────

# 1. Obtener la ruta al CSV
if (-not $Csv) {
    Write-Step "Selecciona el CSV a subir..."
    $Csv = Select-Csv
}

if (-not (Test-Path $Csv)) {
    Write-Err "Archivo no encontrado: $Csv"
    exit 1
}

$nombreArchivo = [System.IO.Path]::GetFileName($Csv)
Write-Step "Archivo seleccionado: $nombreArchivo"

# 2. Resolver la fuente
if (-not $Fuente) {
    $Fuente = Detect-Fuente $nombreArchivo
    if ($Fuente) {
        Write-Info "Fuente detectada automaticamente: $Fuente"
    } else {
        $Fuente = Ask-Fuente $nombreArchivo
    }
}

$fuentesValidas = @("facebook", "tiktok", "youtube", "twitter", "fb_parlamentarias", "external")
if ($Fuente -notin $fuentesValidas) {
    Write-Err "Fuente '$Fuente' no reconocida. Validas: $($fuentesValidas -join ', ')"
    exit 1
}

Write-Info "Fuente: $Fuente"
Write-Info "Storage: $(if ($SubirStorage) { 'si (bucket bronze-raw)' } else { 'no (solo DB)' })"

# 3. Armar el comando e2e
$cmd = @(
    "run", "python", "-m", "data_pipeline.loaders.cli",
    "e2e",
    "--csv", $Csv,
    "--source", $Fuente,
    "--no-archive"
)
if ($SubirStorage) { $cmd += "--upload-to-storage" }

Write-Step "Corriendo pipeline Bronze -> Silver -> Gold..."
Write-Host "    $ uv $($cmd -join ' ')" -ForegroundColor DarkGray

Push-Location $root
try {
    & uv @cmd
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Ok "Pipeline completado para '$nombreArchivo' (fuente: $Fuente)"
    } else {
        Write-Host ""
        Write-Err "Pipeline termino con error (codigo $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
} catch {
    Write-Err $_.Exception.Message
    exit 1
} finally {
    Pop-Location
}
