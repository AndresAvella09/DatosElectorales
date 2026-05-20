# Estado del proyecto

> Resumen rapido. La spec completa esta en `Plan_DataOps_Electoral_2026.docx`.
> Ultima actualizacion: 2026-05-10.

## Hitos (§14 del plan)

| # | Hito | Estado |
|---|---|---|
| H1 | Supabase schema vivo | ✅ aplicado contra prod (us-east-1) |
| H2 | Pipeline E2E automatico (CSV inbox -> raw/silver/gold) | ✅ funcional via watcher |
| H3 | Quality Gate bloqueante | ⏳ pendiente (A4) |
| H4 | Orquestacion + observabilidad | ⏳ pendiente (A5 + A10) |
| H5 | Front React leyendo Gold | ⏳ pendiente (A8) |
| H6 | CI/CD verde | ⏳ pendiente (A9) |

## Agentes (§15 del plan)

| ID | Tarea | Estado | Notas |
|----|---|---|---|
| A1 | Migraciones SQL + RLS + buckets | ✅ aplicado | 8 migraciones + raw_videos. `infra/supabase/migrations/`. |
| A2 | Loaders Bronze/Silver/Gold | ✅ verificado E2E | `data_pipeline/loaders/`. CLI: `python -m data_pipeline.loaders.cli`. |
| A3 | File watcher | ✅ verificado E2E | `data_pipeline/ingestion/watcher.py`. Routea `*_videos.csv` aparte. |
| A4 | Quality Gate hardening | ⏳ no empezado | Extender `data_pipeline/quality/checks.py`. |
| A5 | Flows Prefect | ⏳ no empezado | `data_pipeline/flows/`. |
| A6 | Docker stack | ✅ build OK | `infra/docker/{api,web,worker,scraper}.Dockerfile` + compose ampliado. |
| A7 | API endpoints FastAPI | 🚧 en curso (rama `feature/A7-api-endpoints`) | Routers `health`, `metrics`, `quality`, `runs`. |
| A8 | Front React | ⏳ no empezado | `apps/web/` esta vacio. |
| A9 | CI/CD GitHub Actions | ⏳ no empezado | `.github/workflows/`. |
| A10 | Logger JSON + alertas + v_pipeline_health | 🟡 parcial | La vista `public.v_pipeline_health` existe; falta logger JSON estructurado y webhook de alertas. |

## Extra fuera del plan (necesario para el flujo)

| Pieza | Estado |
|---|---|
| Scrapers TikTok + YouTube integrados al monorepo | ✅ `packages/scrapers/{tiktok,youtube}/` |
| Mappers tiktok/youtube/twitter/external en orchestrator | ✅ |
| Tablas `raw.youtube_videos` + `raw.tiktok_videos` | ✅ aplicadas |
| Helper `apply_migrations.py` (psycopg + `_migrations_applied`) | ✅ |
| `.env` mergeado con 4 keys YouTube + ms_token TikTok + DB URL pooler | ✅ |

## Infraestructura activa

- **Supabase**: proyecto `jsiwjutbyorhqfksjsrf` (us-east-1, t4g.nano).
  Schemas `raw, silver, gold, ops, public` expuestos a PostgREST.
- **Docker compose**: api + prefect + worker arrancan con
  `docker compose -f infra/docker-compose.yml up -d`. Web y
  scraper-runner detras de profiles.

## Como correr el flujo end-to-end hoy

```powershell
# 1. Scrapear (deja CSV en data/inbox/<source>/<date>/)
uv run python -m packages.scrapers.youtube.youtube
uv run python -m packages.scrapers.tiktok.scrape_tiktok

# 2. Watcher procesa y sube a Supabase solo
uv run python -m data_pipeline.ingestion.watcher --scan-on-start
```

## Deuda tecnica conocida (§18 del plan + nuevas)

- `gold.refresh_views()` es no-op (falta RPC en Supabase).
- Watcher mueve a `data/processed/` en lugar de borrar (por diseno; cambiar
  `archive=True` -> `delete=True` si se quiere "nada local").
- `_videos.csv` files que no son youtube/tiktok se ignoran y archivan.
- Logger no estructurado (A10 deuda).
- Sin tests automatizados (deuda).
- `uv.lock` puede traer deps de A7 (in-progress) hasta que esa rama mergee.

## Branches activas

| Rama | Contenido | ¿Pushed? |
|---|---|---|
| `main` | Todo lo mergeado (A1-A6, A2, A3, scrapers, raw_videos) | ✅ origin/main |
| `feature/A7-api-endpoints` | Endpoints FastAPI (en progreso) | local |
| `feat/tiktok-pipeline` | Trabajo viejo de TikTok pre-integracion | ✅ origin/feat/tiktok-pipeline |

Las ramas `feature/A1-supabase-schema`, `feature/A2-loaders-supabase`,
`feature/A3-ingestion-watcher`, `feature/A6-docker-stack`,
`feature/scrapers-integration`, `feature/raw-videos-tables` ya estan
mergeadas a main; se pueden borrar localmente cuando se quiera.
