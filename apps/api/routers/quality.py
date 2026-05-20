"""
/v1/quality — Reportes del Quality Gate (ops.quality_reports).

Cada run que pasa por Silver produce una fila en ops.quality_reports
con overall PASS|WARN|FAIL. Si overall=FAIL, el run termina con
status=quality_failed y Gold no se toca (ver Plan §8).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from apps.api.deps import get_supabase
from apps.api.models import QualityLayer, QualityList, QualityOverall, QualityReport

router = APIRouter(prefix="/v1/quality", tags=["quality"])


def _row_to_report(row: dict[str, Any]) -> QualityReport:
    from datetime import datetime

    created_at = row["created_at"]
    if isinstance(created_at, str) and created_at.endswith("Z"):
        created_at = created_at[:-1] + "+00:00"

    return QualityReport(
        run_id=row["run_id"],
        layer=row["layer"],
        overall=row["overall"],
        checks=row.get("checks") or [],
        created_at=datetime.fromisoformat(created_at),
    )


@router.get("", response_model=QualityList)
async def list_reports(
    run_id: str | None = Query(None, description="Filtra por run_id especifico"),
    layer: str | None = Query(None, description="silver | gold"),
    overall: str | None = Query(None, description="PASS | WARN | FAIL"),
    limit: int = Query(50, ge=1, le=500),
    sb: Client = Depends(get_supabase),
) -> QualityList:
    try:
        q = (
            sb.schema("ops")
            .table("quality_reports")
            .select("run_id,layer,overall,checks,created_at")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if run_id:
            q = q.eq("run_id", run_id)
        if layer:
            q = q.eq("layer", layer)
        if overall:
            q = q.eq("overall", overall)
        rows = q.execute().data or []
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc

    items = [_row_to_report(r) for r in rows]
    return QualityList(items=items, count=len(items))


@router.get("/{run_id}", response_model=QualityList)
async def reports_for_run(run_id: str, sb: Client = Depends(get_supabase)) -> QualityList:
    """Atajo: todos los reportes (silver + gold) de un run."""
    try:
        res = (
            sb.schema("ops")
            .table("quality_reports")
            .select("run_id,layer,overall,checks,created_at")
            .eq("run_id", run_id)
            .order("layer")
            .execute()
        )
        rows = res.data or []
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=404, detail=f"sin reportes para run_id {run_id}")

    items = [_row_to_report(r) for r in rows]
    return QualityList(items=items, count=len(items))
