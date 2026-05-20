"""
deps.py — Dependencias compartidas de la API FastAPI.

Centraliza el cliente Supabase y utilidades que los routers reusan. El
cliente usa SUPABASE_SERVICE_ROLE_KEY (bypassa RLS); por eso esta API
nunca debe exponerse directamente a usuarios finales. El front consume
las vistas public.v_* via supabase anon key directamente.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException, status
from supabase import Client, create_client

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from logger import get_logger  # noqa: E402

log = get_logger("api.deps")

load_dotenv()

_client: Client | None = None


def get_supabase() -> Client:
    """Cliente Supabase singleton (service_role)."""
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY no configuradas. Ver .env.example.",
        )

    log.info("Inicializando cliente Supabase contra %s", url)
    _client = create_client(url, key)
    return _client


def reset_supabase() -> None:
    """Util para tests: limpia el singleton."""
    global _client
    _client = None
