# Estado del proyecto

> Resumen rapido. La spec completa esta en `Plan_DataOps_Electoral_2026.docx`.
> Ultima actualizacion: 2026-05-11.

## Hitos (§14 del plan)

| # | Hito | Estado |
|---|---|---|
| H1 | Supabase schema vivo | ✅ aplicado contra prod (us-east-1) |
| H2 | Pipeline E2E automatico (CSV inbox -> raw/silver) | ✅ funcional via watcher + Prefect |
| H3 | Quality Gate bloqueante | ✅ 5 checks + reporte persistido + bloqueo en `pipeline_e2e` |
| H4 | Orquestacion + observabilidad | 🟡 parcial — Prefect server + flows operativos; falta logger JSON + alertas |
| H5 | Front React leyendo Gold | ⏳ pendiente (A8) |
| H6 | CI/CD verde | ⏳ pendiente (A9) |

## Agentes (§15 del plan)

| ID | Tarea | Estado | Notas |
|----|---|---|---|
| A1 | Migraciones SQL + RLS + buckets | ✅ aplicado | 8 migraciones + raw_videos. `infra/supabase/migrations/`. |
| A2 | Loaders Bronze/Silver/Gold | ✅ verificado E2E | `data_pipeline/loaders/`. Bronze ahora deduplica por `id` antes del UPSERT. |
| A3 | File watcher | ✅ verificado E2E | `data_pipeline/ingestion/watcher.py`. Ahora dispara flows de Prefect (no loaders directos). |
| A4 | Quality Gate hardening | ✅ completo | 5 checks (completeness, freshness, volume, schema, pii_leak) en `data_pipeline/quality/checks.py`. Persiste a `ops.quality_reports` y `ops.pipeline_runs.quality_summary` via `gate.py`. Bloqueo real en `pipeline_e2e` (FAIL → `quality_failed`, gold no se toca). |
| A5 | Flows Prefect | ✅ operativo | `data_pipeline/flows/`: `pipeline_e2e` (silver-only por default), `bronze_to_silver`, `quality_gate`, `ingest_videos`, `refresh_views`. |
| A6 | Docker stack | ✅ stack arriba | `prefect` + `worker` + `api` en compose. UI Prefect en `:4200`. |
| A7 | API endpoints FastAPI | 🚧 en curso (rama `feature/A7-api-endpoints`) | Routers `health`, `metrics`, `quality`, `runs`. |
| A8 | Front React | ⏳ no empezado | `apps/web/` esta vacio. |
| A9 | CI/CD GitHub Actions | ⏳ no empezado | `.github/workflows/`. |
| A10 | Logger JSON + alertas + v_pipeline_health | 🟡 parcial | La vista `public.v_pipeline_health` existe; falta logger JSON estructurado y webhook de alertas. |

## Cambios recientes (rama `feature/A5-prefect-flows`)

- **Flows Prefect operativos** (A5): cada CSV ingerido genera un FlowRun visible en la UI (`http://localhost:4200`) con su task graph: `bronze.load_csv → bronze_to_silver → quality_gate`. Errores quedan en rojo con traceback.
- **Watcher refactorizado** (A3): ya no llama a los loaders directos; invoca `pipeline_e2e(...)` para que Prefect registre cada corrida.
- **`pipeline_e2e` con `skip_gold=True` por default**: el flujo automatico se detiene tras Silver mientras Gold madura.
- **Bronze deduplica por `id`** antes del UPSERT (`raw.posts`) — evita el error de PostgREST "ON CONFLICT DO UPDATE cannot affect row a second time" en CSV con IDs repetidos.
- **A6 cerrado**: `infra/docker/worker.Dockerfile` + servicio `prefect` (server + UI) en compose. `scripts/start.ps1` levanta todo con un comando.
- **Scripts de scraping**: `scripts/scrape_youtube.ps1` y `scripts/scrape_tiktok.ps1`.
- **Smoke tests** en `tests/flows/test_pipeline_e2e_smoke.py`.

## Infraestructura activa

- **Supabase**: proyecto `jsiwjutbyorhqfksjsrf` (us-east-1, t4g.nano).
  Schemas `raw, silver, gold, ops, public` expuestos a PostgREST.
- **Docker compose**: `prefect` (UI :4200) + `worker` (watcher) + `api` (:8000) arrancan con `.\scripts\start.ps1`.
  Scrapers detras de profile `scrapers` (no arrancan automatico — corren en local para usar API keys / cookies del browser).

## Como correr el flujo end-to-end hoy

```powershell
# 1. Levantar el stack (primera vez con -Rebuild)
.\scripts\start.ps1 -Rebuild

# 2. Scrapear (CSV cae en data/inbox/<source>/<date>/)
.\scripts\scrape_youtube.ps1
.\scripts\scrape_tiktok.ps1 eleccionescolombia2026 60

# 3. Watcher procesa automatico. UI: http://localhost:4200
```

Guia paso a paso para clonadores nuevos: ver `GUIA_E2E.md`.

## Deuda tecnica conocida (§18 del plan + nuevas)

- `gold.refresh_views()` es no-op (falta RPC en Supabase). El flow `silver_to_gold` existe pero `pipeline_e2e` salta Gold por default (`skip_gold=True`).
- Logger no estructurado (A10 deuda).
- Sin webhook de alertas en `quality_failed` (A10).
- A7 (endpoints API) sigue en su rama, no mergeado.
- `_videos.csv` files que no son youtube/tiktok se ignoran y archivan.

## Branches activas

| Rama | Contenido | ¿Pushed? |
|---|---|---|
| `main` | Stack base (A1-A3, A6 parcial, raw_videos, scrapers integrados) | ✅ origin/main |
| `develop` | Integracion antes de main | ✅ origin/develop |
| `feature/A5-prefect-flows` | Flows Prefect + A6 cerrado + scripts | local → push a `develop` |
| `feature/A7-api-endpoints` | Endpoints FastAPI (en progreso) | local |

Las ramas `feature/A1-supabase-schema`, `feature/A2-loaders-supabase`,
`feature/A3-ingestion-watcher`, `feature/A6-docker-stack`,
`feature/scrapers-integration`, `feature/raw-videos-tables` ya estan
mergeadas a main; se pueden borrar localmente cuando se quiera.
