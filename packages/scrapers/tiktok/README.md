# TikTok Scraper

Scrapea videos + comentarios de un hashtag y los deja como CSV en
`data/inbox/tiktok/<YYYY-MM-DD>/`. Desde ahi el A2 loader los promueve a
`raw.posts -> silver.posts -> gold.features`.

> El TikTokApi vendored y el `supabase_sync.py` legacy estan en este mismo
> directorio. El pipeline canonico ya **no** escribe a `tiktok_videos`/
> `tiktok_comments` (tablas planas). Para volver a ese comportamiento,
> activar `SUPABASE_LEGACY_SYNC=1`.

---

## Requirements

- Python 3.11+
- Acceso a `tiktok.com` (cuenta logueada en Chrome o Firefox para sacar
  el `msToken` automaticamente).

---

## Variables de entorno (`.env` en la raiz del repo)

| Variable                | Descripcion                                                                |
| ----------------------- | -------------------------------------------------------------------------- |
| `ms_token`              | TikTok session token. Vacio = se autodetecta del navegador.                |
| `HASHTAG`               | Hashtag a scrapear (default `eleccionescolombia2026`).                     |
| `VIDEO_COUNT`           | Max videos por corrida (default `60`).                                     |
| `SKIP_KNOWN_VIDEOS`     | `1` para no revisitar videos ya scrapeados (default `0`).                  |
| `INBOX_DIR`             | Override de `data/inbox/`. Util para tests.                                |
| `SUPABASE_LEGACY_SYNC`  | `1` para upsert directo a `tiktok_videos`/`tiktok_comments`. Default `0`.  |

### Como conseguir `ms_token`

1. Abre [tiktok.com](https://www.tiktok.com) en Chrome o Firefox y loguea.
2. DevTools -> Application -> Cookies -> `https://www.tiktok.com`.
3. Copia el valor de la cookie `msToken`.
4. Pega como `ms_token=<value>` en tu `.env`.

> Si lo dejas vacio, el scraper trata de leerlo del navegador
> automaticamente y, si falla, lo saca con un Playwright headless.

---

## Instalar deps

Si usas el monorepo entero:

```bash
uv sync
playwright install chromium  # primera vez
```

Si solo quieres este scraper en un venv aparte:

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Correr

Desde la raiz del repo:

```powershell
# Recomendado (monorepo): respeta deps del workspace
uv run python -m packages.scrapers.tiktok.scrape_tiktok

# O directo
uv run python packages\scrapers\tiktok\scrape_tiktok.py
```

> Abrira una ventana de Playwright. Si TikTok muestra CAPTCHA, resuelvelo
> manualmente; el scraper detecta cuando se cierra y continua.

---

## Output

Se escriben CSV en `data/inbox/tiktok/<YYYY-MM-DD>/`:

| Archivo                          | Contenido                              |
| -------------------------------- | -------------------------------------- |
| `run_<HHMMSS>_videos.csv`        | Un row por video (metadata + stats).   |
| `run_<HHMMSS>_comments.csv`      | Un row por comentario.                 |

Re-correr es seguro: filas existentes no se pisan, solo se appendean
nuevas (usa `comment_id` y `video_id` como dedup keys leyendo el CSV ya
escrito).

### Empujar al pipeline (raw -> silver -> gold)

Cuando termine la corrida:

```bash
uv run python -m data_pipeline.loaders.cli e2e \
    --csv data/inbox/tiktok/2026-05-10/run_120000_comments.csv \
    --source tiktok
```

---

## Tablas legacy (opt-in)

Solo si `SUPABASE_LEGACY_SYNC=1`, el scraper hace upsert directo a:

**`tiktok_videos`**

| Column           | Type      |
| ---------------- | --------- |
| hashtag          | text      |
| video_id         | text (PK) |
| create_time      | timestamp |
| author_unique_id | text      |
| author_nickname  | text      |
| desc             | text      |
| play_count       | int       |
| digg_count       | int       |
| comment_count    | int       |
| share_count      | int       |
| video_duration   | int       |

**`tiktok_comments`**

| Column         | Type      |
| -------------- | --------- |
| video_id       | text (FK) |
| comment_id     | text (PK) |
| create_time    | timestamp |
| user_unique_id | text      |
| user_nickname  | text      |
| text           | text      |
| digg_count     | int       |
| reply_count    | int       |

Estas tablas no estan declaradas en `infra/supabase/migrations/` (el
modelo nuevo es `raw.posts`). Si las necesitas, creales con un
`CREATE TABLE` manual o vuelve al pipeline canonico.
