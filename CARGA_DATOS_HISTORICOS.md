# Carga de datos históricos a Supabase

Ejecutar en orden. Requiere `.env` con `SUPABASE_URL` y `SUPABASE_KEY`.

## 0. Aplicar migración SQL en Supabase

Ejecutar el contenido de `infra/supabase/migrations/20260512120000__silver_author_id.sql`
en el SQL Editor de Supabase (renombra `username_hash` → `author_id` en `silver.posts`).

## 1. Videos de TikTok → raw.tiktok_videos

```bash
uv run python -m data_pipeline.loaders.cli videos \
  --csv "data/todos/todos datos proyecto elecciones/tiktok_videos.csv" \
  --source tiktok
```

## 2. Videos de YouTube → raw.youtube_videos

```bash
uv run python -m data_pipeline.loaders.cli videos \
  --csv "data/todos/todos datos proyecto elecciones/youtube_videos_anonymized.csv" \
  --source youtube
```

## 3. Comentarios TikTok → raw.posts + silver + gold (~44k filas)

```bash
uv run python -m data_pipeline.loaders.cli e2e \
  --csv "data/todos/todos datos proyecto elecciones/tiktok_comments.csv" \
  --source tiktok \
  --no-archive
```

## 4. Comentarios YouTube → raw.posts + silver + gold (~13k filas)

```bash
uv run python -m data_pipeline.loaders.cli e2e \
  --csv "data/todos/todos datos proyecto elecciones/youtube_data_anonymized.csv" \
  --source youtube \
  --no-archive
```

## 5. Tweets → raw.posts + silver + gold (~5.3k filas)

```bash
uv run python -m data_pipeline.loaders.cli e2e \
  --csv "data/todos/todos datos proyecto elecciones/tweets_colombia_anonymized.csv" \
  --source twitter \
  --no-archive
```

## 6. Comentarios Facebook → raw.posts + silver + gold (~29k filas)

```bash
uv run python -m data_pipeline.loaders.cli e2e \
  --csv "data/todos/todos datos proyecto elecciones/facebook_comments (5)_limpio.csv" \
  --source facebook \
  --no-archive
```

## Total esperado

| Tabla | Filas aprox. |
|---|---|
| `raw.tiktok_videos` | 224 |
| `raw.youtube_videos` | 16.984 |
| `raw.posts` (bronze) | 92.479 |
| `silver.posts` | ~92.000 (sin duplicados) |
| `gold.features` | ~92.000 |
