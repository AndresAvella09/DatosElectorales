"""
/health — Liveness + readiness check.

- Liveness: el proceso responde.
- Readiness: Supabase configurado y accesible (toca una vista publica
  barata: public.v_pipeline_health con limit 1).

Diseno: nunca lanza 5xx; cuando algo va mal, retorna 200 con
status="degraded" + detail, para que orquestadores y dashboards
distingan "API muerta" (no responde) de "API arriba pero downstream
roto".
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from supabase import Client

from apps.api.deps import get_supabase
from apps.api.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(sb: Client = Depends(get_supabase)) -> HealthResponse:
    env = os.getenv("ENVIRONMENT", "development")
    try:
        sb.table("v_pipeline_health").select("run_id").limit(1).execute()
        reachable = True
        detail = None
    except Exception as exc:  # noqa: BLE001
        reachable = False
        detail = f"degraded: {exc}"

    return HealthResponse(
        status="ok" if reachable else "degraded",
        timestamp=datetime.now(timezone.utc),
        environment=env,
        supabase_reachable=reachable,
        detail=detail,
    )
