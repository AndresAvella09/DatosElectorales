# ── API ──────────────────────────────────
FROM python:3.11-slim AS api

WORKDIR /app
COPY pyproject.toml ./
COPY packages/contracts ./packages/contracts
COPY packages/logger ./packages/logger
COPY apps/api ./apps/api

RUN pip install --no-cache-dir uv && uv sync --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
