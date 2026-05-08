# ── Scraper Worker Pesado (Twitter/Playwright) ──
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app
COPY packages/scrapers/twitter ./packages/scrapers/twitter
COPY packages/contracts ./packages/contracts
COPY packages/logger ./packages/logger
COPY data_pipeline ./data_pipeline

RUN pip install --no-cache-dir -r packages/scrapers/twitter/requirements.txt \
    && pip install --no-cache-dir pydantic pandas \
    && playwright install chromium

CMD ["python", "packages/scrapers/twitter/twitterScrape.py", "--help"]
