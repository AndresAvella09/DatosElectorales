# Usage: .\run_tiktok.ps1 [HASHTAG] [VIDEO_COUNT]
# Example: .\run_tiktok.ps1 eleccionescolombia2026 60
# Falls back to .env values when args are omitted.
#
# Asume que tienes 'uv' instalado y el monorepo sincronizado:
#   uv sync
#   uv run playwright install chromium   # primera vez

$ErrorActionPreference = "Stop"

if ($args[0]) { $env:HASHTAG     = $args[0] }
if ($args[1]) { $env:VIDEO_COUNT = $args[1] }

Write-Host "[run] Starting TikTok scraper..."
uv run python -m packages.scrapers.tiktok.scrape_tiktok
