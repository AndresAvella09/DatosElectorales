# API — Backend (FastAPI)

Ejecutar localmente:

```bash
uv run uvicorn apps.api.main:app --reload --port 8000
```

Docs interactivos: http://localhost:8000/docs

## Endpoints

| Metodo | Path | Descripcion |
|--------|------|-------------|
| GET | `/health` | Liveness + readiness (toca Supabase) |
| GET | `/api/v1/status` | Estado general del pipeline |
| GET | `/v1/runs` | Lista corridas (`?status=`, `?flow_name=`, `?hours=`) |
| GET | `/v1/runs/{run_id}` | Corrida especifica |
| GET | `/v1/quality` | Reportes Quality Gate (`?run_id=`, `?layer=`, `?overall=`) |
| GET | `/v1/quality/{run_id}` | Todos los reportes de un run |
| GET | `/v1/metrics` | Resumen operativo agregado |
| GET | `/v1/metrics/sources_volume_7d` | Volumen por fuente (7d) |
| GET | `/v1/metrics/last_success_by_flow` | Ultimo run exitoso por flow |
| GET | `/v1/metrics/sentiment_daily` | Sentiment diario por fuente |
| GET | `/v1/metrics/quality_failed_rate` | Tasa de fallos en 24h y 7d |

## Tests

```bash
pytest apps/api/tests/ -v
```

Los tests usan un `FakeClient` que emula la API encadenada de supabase-py —
no requieren conexion a Supabase real.
