# Guia E2E — YouTube y TikTok

Pipeline automatico desde scraping hasta Silver en Supabase.
Tras los pasos de setup, todo el ciclo se ejecuta con **3 comandos**.

---

## 0. Setup (una sola vez)

Necesitas: Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker Desktop, una cuenta de Supabase.

```powershell
# Clonar e instalar dependencias
git clone https://github.com/AndresAvella09/DatosElectorales.git
cd DatosElectorales
uv sync

# Variables de entorno
copy .env.example .env
# Edita .env y completa:
#   SUPABASE_URL=...
#   SUPABASE_SERVICE_ROLE_KEY=...
#   SUPABASE_DB_URL=postgresql://...   (para aplicar migraciones)
#   YOUTUBE_API_KEY=...                (1 o varias: YOUTUBE_API_KEY1, ...2)
#   ms_token=...                       (TikTok; opcional, se autodetecta de cookies)

# Aplicar migraciones (crea schemas raw/silver/gold/ops + buckets + RLS)
uv run python infra/supabase/apply_migrations.py

# Primera vez para TikTok (Playwright)
uv run playwright install chromium
```

---

## 1. Levantar el stack (Prefect + watcher + API)

```powershell
.\scripts\start.ps1 -Rebuild
```

Esto deja corriendo en background:

- **Prefect UI** — `http://localhost:4200` (ver corridas, grafos, errores)
- **Watcher** — observa `data/inbox/` y procesa cada CSV que aparezca
- **API** — `http://localhost:8000`

> La primera vez tarda unos minutos compilando imagenes. Las siguientes:
> `.\scripts\start.ps1` (sin `-Rebuild`).

---

## 2. Ingesta — corre el scraper

### YouTube

```powershell
.\scripts\scrape_youtube.ps1
```

> Las palabras clave estan en `packages/scrapers/youtube/youtube.py` (variable `YOUTUBE_QUERIES`). Editar ahi.

### TikTok

```powershell
.\scripts\scrape_tiktok.ps1 eleccionescolombia2026 60
#                            ^^^^^^^^^^^^^^^^^^^^^^^ ^^
#                            hashtag                 cantidad de videos
```

**Que pasa:**
El scraper escribe el CSV en:

```
data/inbox/<source>/<YYYY-MM-DD>/run_<HHMMSS>_comments.csv
data/inbox/<source>/<YYYY-MM-DD>/run_<HHMMSS>_videos.csv
```

donde `<source>` es `youtube` o `tiktok`.

---

## 3. Procesamiento automatico — monitoreas en Prefect

No tienes que hacer nada. Apenas el CSV aparece en `data/inbox/`, el `watcher` lo detecta y dispara el flow `pipeline_e2e` que hace:

```
bronze.load_csv  ─►  bronze_to_silver  ─►  quality_gate
   (raw.posts)        (silver.posts)        (ops.quality_reports)
```

**Abre la UI de Prefect** y ve la corrida en vivo:

> http://localhost:4200

Cada CSV genera un FlowRun. Click en el run → ves el grafo tipo Airflow con los tasks en verde/rojo y los logs de cada uno. Si algo falla, el task rojo te dice exactamente donde.

---

## Verificar que los datos llegaron

En Supabase Studio (SQL editor):

```sql
-- Ultimas corridas y estado
select run_id, flow_name, status, rows_in, rows_out, started_at
from ops.pipeline_runs
order by started_at desc
limit 10;

-- Reporte de calidad de la ultima corrida
select * from ops.quality_reports order by created_at desc limit 1;

-- Datos en bronze y silver
select count(*) from raw.posts;
select count(*) from silver.posts;
```

---

## Apagar el stack

```powershell
.\scripts\start.ps1 -Down
```

Los CSVs procesados quedan en `data/processed/<fecha>/`. La data ya esta en Supabase.
