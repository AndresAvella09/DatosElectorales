# YouTube Scraper

Recolecta videos + comentarios + replies de YouTube para discurso electoral
colombiano, con **rotacion de API keys** para drenar la cuota diaria
combinada de varias keys.

## Configuracion

En el `.env` de la raiz del repo:

```dotenv
# Una o varias keys. El scraper rota automaticamente cuando una pega
# quotaExceeded. El sufijo numerico define el orden.
YOUTUBE_API_KEY1=AIza...
YOUTUBE_API_KEY2=AIza...
YOUTUBE_API_KEY3=AIza...
YOUTUBE_API_KEY4=AIza...

# Opcional: solo si quieres seguir escribiendo a la tabla legacy
# (youtube_comments / youtube_videos). Por defecto APAGADO; el pipeline
# canonico es CSV en data/inbox + A2 loaders.
SUPABASE_LEGACY_SYNC=0
```

Como conseguir una API key:
https://console.cloud.google.com/apis/library/youtube.googleapis.com (cada
proyecto Google Cloud te da 10,000 unidades/dia gratis).

## Instalar deps

Si usas el monorepo entero, ya estan en `pyproject.toml` raiz:

```bash
uv sync
```

Si solo quieres este scraper en un venv aparte:

```bash
pip install -r requirements.txt
```

## Correr

```bash
uv run python -m packages.scrapers.youtube.youtube
# o desde el directorio del scraper:
python youtube.py
```

## Salida

Por defecto escribe en `data/inbox/youtube/<YYYY-MM-DD>/`:

- `run_<HHMMSS>_comments.csv` — un row por comentario o reply.
- `run_<HHMMSS>_videos.csv`   — un row por video con metadata + stats.

El esquema de `comments.csv` ya esta mapeado por
`data_pipeline/ingestion/orchestrator.py` (mapeador `youtube`), asi que
queda listo para el A2 loader:

```bash
uv run python -m data_pipeline.loaders.cli e2e \
    --csv data/inbox/youtube/2026-05-10/run_120000_comments.csv \
    --source youtube
```

## Tunables

Editar al principio de `youtube.py`:

| Variable                          | Default                                | Que hace |
|-----------------------------------|----------------------------------------|---|
| `YOUTUBE_QUERIES`                 | 3 queries electorales                   | Lista de queries a buscar. |
| `YOUTUBE_MAX_VIDEOS_PER_QUERY`    | `None` (paginar todo)                  | Cap de videos por query. |
| `YOUTUBE_MAX_COMMENTS_PER_VIDEO`  | `None`                                 | Cap de top-level comments por video. |
| `YOUTUBE_MAX_REPLIES_PER_COMMENT` | `None`                                 | Cap de replies por comentario. |
| `YOUTUBE_PUBLISHED_WITHIN_DAYS`   | `60`                                   | Solo videos publicados en ultimos N dias. `None` = sin filtro. |

## Costo en cuota (referencia API v3)

| Operacion                      | Unidades |
|--------------------------------|----------|
| `search.list`                  | 100 / pagina (50 ids) |
| `videos.list` (statistics+...) | 1 / video |
| `commentThreads.list`          | 1 / pagina (100 comments) |
| `comments.list` (replies)      | 1 / pagina (100 replies) |

Con 4 keys y 10k unidades/dia cada una = 40k unidades/dia. Una corrida
tipica con 200 videos consume ~3-5k.
