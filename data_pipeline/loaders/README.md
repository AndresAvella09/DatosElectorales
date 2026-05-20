# Loaders — UPSERT a Supabase

Modulos que **escriben** datos en Supabase. Implementan las etapas 1, 2
y 4 del pipeline (§7 del plan).

```
data_pipeline/loaders/
├── _client.py        # Singleton supabase-py (service_role)
├── runs.py           # ops.pipeline_runs: start() / finish()
├── bronze.py         # CSV -> Storage + raw.posts
├── silver.py         # raw.posts -> silver.posts (clean + anonymize)
├── gold.py           # silver.posts -> gold.features
├── cli.py            # Invocacion manual (python -m ...)
└── README.md
```

## Requisitos

- `.env` con:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY` (la **secret**, no la anon)
- Migraciones de A1 ya aplicadas en Supabase (schemas `raw`, `silver`,
  `gold`, `ops` + buckets).

## Uso programatico

```python
from data_pipeline.loaders import bronze, silver, gold, runs

run_id = runs.start("ingest_inbox", rows_in=320)
try:
    n = bronze.load_csv(
        "data/inbox/twitter/2026-05-10/run_120000.csv",
        source="twitter",
        run_id=run_id,
    )
    silver.promote_run(run_id)
    gold.promote_run(run_id, refresh=True)
    runs.finish(run_id, status="success", rows_out=n)
except Exception as e:
    runs.finish(run_id, status="failed", error=str(e))
    raise
```

## Uso por CLI

```bash
# 1. Ver que CSVs hay pendientes
uv run python -m data_pipeline.loaders.cli scan

# 2. Pipeline completo para un CSV
uv run python -m data_pipeline.loaders.cli e2e \
    --csv data/inbox/twitter/2026-05-10/run_120000.csv \
    --source twitter

# 3. Solo bronze (devuelve un run_id que puedes reusar)
uv run python -m data_pipeline.loaders.cli bronze \
    --csv data/inbox/youtube/2026-05-10/run_120000.csv \
    --source youtube

# 4. Solo silver/gold de un run existente
uv run python -m data_pipeline.loaders.cli silver --run-id <uuid>
uv run python -m data_pipeline.loaders.cli gold   --run-id <uuid>
```

## Idempotencia

| Capa | Estrategia |
|---|---|
| Bronze | sha256 del archivo: si ya esta en `raw.posts.source_sha256`, se salta. UPSERT por `id`. |
| Silver | UPSERT por `(id, cleaned_at)`. Reprocesar el mismo run sobreescribe; reprocesar en otro run agrega nueva version. |
| Gold | UPSERT por `id`. Reprocesar pisa los features. |
| Storage | `upsert=true` en el upload; reintentos no fallan. |

## Verificar que funciono

Despues de un `e2e`, en el SQL Editor de Supabase:

```sql
-- 1. Datos llegaron a las tres capas con el mismo run_id?
select 'raw'   as layer, count(*) from raw.posts    where run_id = '<uuid>'
union all select 'silver',         count(*) from silver.posts where run_id = '<uuid>'
union all select 'gold',           count(*) from gold.features where run_id = '<uuid>';

-- 2. Run quedo registrado?
select run_id, flow_name, status, rows_in, rows_out,
       finished_at - started_at as duration
from ops.pipeline_runs where run_id = '<uuid>';

-- 3. Vista publica refleja los datos
select * from public.v_pipeline_health limit 5;
```

## Limitaciones conocidas

- `gold.refresh_views()` es no-op: `REFRESH MATERIALIZED VIEW` requiere
  una RPC en Supabase que A1 todavia no expone. Hacerlo manual desde el
  SQL Editor cuando metas datos: `refresh materialized view public.v_sentiment_daily;`
- Los loaders usan PostgREST via supabase-py. Si UPSERTeas mas de
  ~10k filas en una sola llamada, pega los limites de PostgREST. El
  chunking interno (200 rows) lo evita en uso normal.
- `langdetect` no es determinista por defecto. Lo seedeamos con `0`,
  pero textos cortos siguen siendo poco fiables.

## Quien me llama

| Llamador | Cuando |
|---|---|
| **Manual / CLI** | Pruebas, backfills, ad-hoc. |
| **A3 watcher** | Detecta CSV en `data/inbox/` y llama `bronze.load_csv()`. |
| **A5 flows Prefect** | `ingest_inbox`, `bronze_to_silver`, `silver_to_gold` envuelven estas funciones con retries. |
