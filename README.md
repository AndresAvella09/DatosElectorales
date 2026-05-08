# DatosElectorales

Sistema modular de **scraping y análisis de sentimiento** para el discurso electoral colombiano (2026).

## Arquitectura

El proyecto sigue una **arquitectura Medallion** (Bronze → Silver → Gold) dentro de un monorepo gestionado con [`uv`](https://docs.astral.sh/uv/).

```
Scrapers (Twitter, YouTube, FB, TikTok)
    ↓
Bronze   — Datos crudos particionados por fuente y fecha
    ↓
Silver   — Datos limpios, deduplicados, sin PII
    ↓
Gold     — Features para ML (NLP, temporal, engagement)
    ↓
ML       — Modelos de sentimiento (equipo externo)
    ↓
API      — FastAPI + Supabase → Dashboard Web
```

## Estructura del Monorepo

| Directorio | Descripción |
|---|---|
| `apps/api` | Backend API (FastAPI + Supabase) |
| `apps/web` | Dashboard web (pendiente) |
| `packages/contracts` | Esquemas Pydantic (Bronze, Silver, Gold) |
| `packages/logger` | Logger centralizado |
| `packages/scrapers/` | Workers de scraping por red social |
| `data_pipeline/` | Pipeline Medallion (ingestion, bronze, silver, gold) |
| `ml/` | Interfaces y wrappers para modelos de ML |
| `infra/` | Docker, Supabase, IaC |

## Requisitos

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (gestor de paquetes)

## Instalación Rápida

```powershell
# 1. Instalar uv (una sola vez)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Sincronizar dependencias del workspace
uv sync

# 3. Copiar variables de entorno
cp .env.example .env
# Editar .env con tus claves (YOUTUBE_API_KEY, SUPABASE_URL, etc.)
```

## Scrapers

Cada scraper es independiente y tiene su propia documentación:

- **Twitter/X:** [`packages/scrapers/twitter/howToUse`](packages/scrapers/twitter/howToUse) — Playwright + Edge
- **YouTube:** [`packages/scrapers/youtube/howToUse.md`](packages/scrapers/youtube/howToUse.md) — API v3
- **Facebook:** Pendiente
- **TikTok:** Pendiente

## Equipo

- **Data Engineering:** Pipeline de datos (ingestion → gold)
- **Data Science / ML:** Modelos de sentimiento (vía `ml/interfaces/`)
- **Backend:** API + Supabase
- **Frontend:** Dashboard web
