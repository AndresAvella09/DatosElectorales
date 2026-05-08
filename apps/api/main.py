"""
main.py — Entrypoint FastAPI (placeholder).

Este es un servidor mínimo que servirá como punto de conexión
entre el pipeline de datos y el frontend/dashboard.

Por ahora solo tiene:
  - GET /health — Health check
  - GET /api/v1/status — Estado del pipeline

Los endpoints reales se agregarán cuando el equipo de frontend
los necesite (consultar sentimiento, datos gold, etc.).

Ejecutar localmente:
    uv run uvicorn apps.api.main:app --reload --port 8000
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(
    title="DatosElectorales API",
    description="API para consultar datos de sentimiento electoral — Colombia 2026",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restringir en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/v1/status")
async def pipeline_status():
    """Estado general del pipeline (placeholder)."""
    return {
        "status": "operational",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "supabase_configured": bool(os.getenv("SUPABASE_URL")),
        "message": "API placeholder — endpoints reales pendientes de implementación.",
    }
