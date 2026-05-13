"""
main.py — Entrypoint FastAPI para DatosElectorales.

Ejecutar localmente:
    uv run uvicorn apps.api.main:app --reload --port 8000

Docs interactivos: http://localhost:8000/docs
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import health, metrics, quality, runs

load_dotenv()

app = FastAPI(
    title="DatosElectorales API",
    description="API para consultar datos de sentimiento electoral — Colombia 2026",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restringir en produccion
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(runs.router)
app.include_router(quality.router)
app.include_router(metrics.router)


@app.get("/api/v1/status")
async def pipeline_status():
    """Estado general del pipeline."""
    return {
        "status": "operational",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "supabase_configured": bool(os.getenv("SUPABASE_URL")),
    }
