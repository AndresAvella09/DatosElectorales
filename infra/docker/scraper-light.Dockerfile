# ── Scraper Worker Ligero (YouTube, APIs) ──
FROM python:3.11-slim

WORKDIR /app
COPY packages/scrapers/youtube ./packages/scrapers/youtube
COPY packages/contracts ./packages/contracts
COPY packages/logger ./packages/logger
COPY data_pipeline ./data_pipeline

RUN pip install --no-cache-dir -r packages/scrapers/youtube/requirements.txt \
    && pip install --no-cache-dir pydantic pandas

CMD ["python", "packages/scrapers/youtube/youtube.py"]
