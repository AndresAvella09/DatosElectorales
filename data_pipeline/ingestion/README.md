# Ingestion

Componentes de la **etapa 0/1** del pipeline (per plan §7).

```
data_pipeline/ingestion/
├── orchestrator.py   # CSV -> RawSocialPost (mappers por fuente)
├── watcher.py        # File watcher: data/inbox/ -> A2 loaders (auto)
└── README.md
```

## Modulos

### `orchestrator.py`
Lee un CSV y lo normaliza a `RawSocialPost`. Tiene mappers para
`twitter`, `youtube`, `tiktok`, `external`. Lo usa el A2 loader
(`bronze.load_csv`) y se puede correr standalone:

```bash
uv run python -m data_pipeline.ingestion.orchestrator \
    --twitter-csv path/to/tweets.csv \
    --youtube-csv path/to/youtube.csv
```

### `watcher.py` (A3)
Vigila `data/inbox/<source>/<YYYY-MM-DD>/*.csv`. Cuando aparece un CSV
nuevo, dispara el pipeline A2 completo (bronze -> silver -> gold) sin
intervencion manual.

```bash
# Daemon: watchdog + safety-net cada 30 min
uv run python -m data_pipeline.ingestion.watcher --scan-on-start

# Modo cron: un solo scan y salir
uv run python -m data_pipeline.ingestion.watcher --once
```

#### Como funciona

1. **Watchdog** detecta `on_created` o `on_moved` en `data/inbox/`.
2. Filtra paths que NO encajen en
   `data/inbox/<source>/<YYYY-MM-DD>/<file>.csv` con
   `<source>` en `{twitter, youtube, tiktok, external}`.
3. Encola el path en una cola FIFO de un solo worker
   (concurrency=1, per plan §9.2).
4. Antes de procesar, **espera que el archivo este estable**
   (mtime y tamano sin cambios por ~2 s) para no leer mientras el
   scraper sigue escribiendo.
5. Crea un `run_id` en `ops.pipeline_runs` (status='running').
6. Ejecuta `bronze.load_csv -> silver.promote_run -> gold.promote_run`
   con el mismo `run_id`.
7. Marca el run como `success` o `failed` y archiva el CSV en
   `data/processed/<YYYY-MM-DD>/`.

#### Safety net

Por defecto, el watcher tambien re-escanea inbox completo cada 30 min
(configurable con `--safety-net-interval N`, en segundos). Esto cubre
el caso de:

- Archivos depositados antes de que arrancara el watcher.
- Eventos de filesystem que watchdog se haya perdido (raro pero pasa
  con bind mounts en Docker, NFS, etc.).

Setear `--safety-net-interval 0` lo desactiva (solo watchdog).

#### Concurrencia

Una sola corrida activa a la vez. Si llegan 5 CSVs simultaneos, se
encolan y procesan en orden. La cola dedupe por path: si el mismo
archivo dispara dos eventos (raro), solo se encola una vez.

#### Que NO hace

- **No borra** el CSV. Lo mueve a `data/processed/` (plan §3
  trazabilidad). Si quieres "nada local", se cambia el flag
  `archive=True` por `delete=True` en `bronze.load_csv` (delta de 1
  linea, no es A3).
- **No re-procesa** archivos en `data/processed/`. Mover de vuelta a
  `inbox/` para reintentar.
- **No corre los scrapers**. Asume que llegan CSVs por su cuenta
  (los scrapers de `packages/scrapers/*` los depositan).

## Tests rapidos

```bash
# Drop un CSV
cp tests/fixtures/twitter_sample.csv \
    data/inbox/twitter/$(date -u +%Y-%m-%d)/run_test.csv

# Watcher inicia, procesa, archiva
uv run python -m data_pipeline.ingestion.watcher --scan-on-start
# Ctrl+C cuando termine
```

Verifica en Supabase: la fila aparece en `raw.posts`, `silver.posts`,
`gold.features`, y la corrida en `ops.pipeline_runs`.
