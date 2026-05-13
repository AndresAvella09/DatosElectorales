"""
/v1/runs — Corridas del pipeline (ops.pipeline_runs).

Lee de la vista public.v_pipeline_health (ultimas 50 corridas) cuando
no se filtra, y de ops.pipeline_runs directamente cuando se pide algo
mas alla. La vista ya tiene duration_seconds calculado.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from apps.api.deps import get_supabase
from apps.api.models import PipelineRun, RunsList, RunStatus

router = APIRouter(prefix="/v1/runs", tags=["runs"])


def _row_to_run(row: dict[str, Any]) -> PipelineRun:
    def _dt(v: str | None) -> datetime | None:
        if not v:
            return None
        return datetime.fromisoformat(v.replace("+00:00", "+00:00"))

    return PipelineRun(
        run_id=row["run_id"],
        flow_name=row["flow_name"],
        status=row["status"],
        started_at=_dt(row["started_at"]),
        finished_at=_dt(row.get("finished_at")),
        duration_seconds=row.get("duration_seconds"),
        rows_in=row.get("rows_in"),
        rows_out=row.get("rows_out"),
        quality_summary=row.get("quality_summary"),
        error=row.get("error"),
    )


@router.get("", response_model=RunsList)
async def list_runs(
    status: str | None = Query(None, description="Filtra por status: running|success|failed|quality_failed"),
    flow_name: str | None = Query(None, description="Filtra por nombre de flow"),
    hours: int | None = Query(None, description="Solo corridas iniciadas en las ultimas N horas"),
    sb: Client = Depends(get_supabase),
) -> RunsList:
    try:
        if status or flow_name or hours:
            q = sb.schema("ops").table("pipeline_runs").select(
                "run_id,flow_name,status,started_at,finished_at,rows_in,rows_out,quality_summary,error"
            ).order("started_at", desc=True).limit(200)
            if status:
                q = q.eq("status", status)
            if flow_name:
                q = q.eq("flow_name", flow_name)
            if hours:
                since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
                q = q.gte("started_at", since)
            rows = q.execute().data or []
        else:
            rows = sb.table("v_pipeline_health").select("*").execute().data or []

        items = [_row_to_run(r) for r in rows]
        return RunsList(items=items, count=len(items))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc


@router.get("/{run_id}", response_model=PipelineRun)
async def get_run(run_id: str, sb: Client = Depends(get_supabase)) -> PipelineRun:
    try:
        res = (
            sb.schema("ops")
            .table("pipeline_runs")
            .select("run_id,flow_name,status,started_at,finished_at,rows_in,rows_out,quality_summary,error")
            .eq("run_id", run_id)
            .execute()
        )
        rows = res.data or []
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=404, detail=f"run_id {run_id} no encontrado")
    return _row_to_run(rows[0])
