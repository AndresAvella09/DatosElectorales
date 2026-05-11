# ── Worker (watcher + Prefect flows) ──────────────────────────────
# Imagen unica que corre:
#   - data_pipeline.ingestion.watcher en modo daemon
#   - cada CSV detectado dispara pipeline_e2e (Prefect flow)
#   - los runs aparecen en la UI del servicio prefect (puerto 4200)
#
# Sin scrapers ni Playwright: el worker solo procesa CSVs que ya
# estan en /app/data/inbox/ (montados desde el host o por otro
# contenedor scraper).
FROM python:3.11-slim AS worker

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Solo lo necesario para el pipeline (no scrapers).
# apps/api se copia porque es workspace member en pyproject.toml,
# aunque el worker no lo ejecute.
COPY pyproject.toml uv.lock ./
COPY packages/contracts ./packages/contracts
COPY packages/logger ./packages/logger
COPY apps/api ./apps/api
COPY data_pipeline ./data_pipeline

RUN pip install --no-cache-dir uv \
 && uv sync --no-dev

# Carpetas que el watcher espera
RUN mkdir -p /app/data/inbox /app/data/processed

# El servicio prefect del compose corre en http://prefect:4200
ENV PREFECT_API_URL=http://prefect:4200/api

CMD ["uv", "run", "python", "-m", "data_pipeline.ingestion.watcher", "--scan-on-start"]
