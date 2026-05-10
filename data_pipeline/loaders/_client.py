"""
_client.py — Singleton del cliente Supabase para el pipeline.

Lee SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY del entorno (o .env). El
service_role bypassa RLS, asi que este cliente NUNCA debe usarse desde
codigo que lleguen a tocar inputs del usuario final.

Uso:
    from data_pipeline.loaders._client import get_client
    sb = get_client()
    sb.schema("raw").table("posts").upsert([...]).execute()
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from logger import get_logger  # noqa: E402

log = get_logger("loaders.client")


@lru_cache(maxsize=1)
def get_client() -> Client:
    """
    Devuelve el cliente Supabase singleton (service_role).

    Lee de variables de entorno:
        SUPABASE_URL              (requerido)
        SUPABASE_SERVICE_ROLE_KEY (requerido)
    """
    load_dotenv(_PROJECT_ROOT / ".env")

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url:
        raise RuntimeError(
            "SUPABASE_URL no esta definida. Configura .env "
            "(ver .env.example) o exporta la variable."
        )
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY no esta definida. Es la key 'secret', "
            "no la 'anon'. Sacala de Supabase Studio -> Settings -> API."
        )

    log.info("Inicializando cliente Supabase contra %s", url)
    return create_client(url, key)


def reset_client() -> None:
    """Util para tests: invalida el singleton para forzar recreacion."""
    get_client.cache_clear()
