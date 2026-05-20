# ── Scraper TikTok (Playwright + TikTokApi vendored) ──────────────────
# Usa la imagen oficial de Playwright para tener Chromium listo.
# En Docker corre headless (TIKTOK_HEADLESS=true). En local puedes
# correrlo directamente con uv para tener la ventana visible y resolver
# captchas manualmente.
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY packages/scrapers/tiktok ./packages/scrapers/tiktok
COPY packages/contracts        ./packages/contracts
COPY packages/logger           ./packages/logger
COPY data_pipeline             ./data_pipeline

RUN pip install --no-cache-dir \
        requests \
        playwright \
        httpx \
        python-dotenv \
        pydantic \
        pandas \
    && playwright install chromium

ENV TIKTOK_HEADLESS=true

CMD ["python", "packages/scrapers/tiktok/scrape_tiktok.py"]
