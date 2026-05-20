"""
/v1/metrics — Metricas operativas agregadas (Plan §10.4).

Consolida en una sola respuesta los datos que el front pinta en la
pagina Overview / Pipeline ops:

  - sources_volume_7d   : volumen por fuente y dia (ultimos 7d)
  - last_success_by_flow: ultima corrida exitosa por flow
  - sentiment_daily     : sentiment promedio diario por fuente
  - quality_failed_rate : tasa de quality_failed en 24h y 7d

Subendpoints individuales /v1/metrics/<nombre> para evitar pagos
innecesarios cuando el front solo necesita un bloque.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from apps.api.deps import get_supabase
from apps.api.models import (
    LastSuccessByFlow,
    MetricsResponse,
    QualityFailedRate,
    SentimentDay,
    SourceVolumeDay,
)

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


def _fetch_sources_volume_7d(sb: Client) -> list[SourceVolumeDay]:
    rows = sb.table("v_sources_volume_7d").select("source,posts").execute().data or []
    return [SourceVolumeDay(source=r["source"], posts=r["posts"]) for r in rows]


def _fetch_last_success(sb: Client) -> list[LastSuccessByFlow]:
    rows = (
        sb.table("v_last_success_by_flow")
        .select("flow_name,run_id,started_at,finished_at,rows_out")
        .execute()
        .data or []
    )
    result = []
    for r in rows:
        result.append(
            LastSuccessByFlow(
                flow_name=r["flow_name"],
                run_id=r["run_id"],
                started_at=datetime.fromisoformat(r["started_at"]),
                finished_at=datetime.fromisoformat(r["finished_at"]) if r.get("finished_at") else None,
                rows_out=r.get("rows_out"),
            )
        )
    return result


def _fetch_sentiment_daily(sb: Client) -> list[SentimentDay]:
    rows = (
        sb.table("v_sentiment_daily")
        .select("source,posts,positive_count,negative_count,neutral_count,avg_sentiment")
        .execute()
        .data or []
    )
    return [
        SentimentDay(
            source=r["source"],
            posts=r["posts"],
            positive_count=r.get("positive_count"),
            negative_count=r.get("negative_count"),
            neutral_count=r.get("neutral_count"),
            avg_sentiment=r.get("avg_sentiment"),
        )
        for r in rows
    ]


def _compute_quality_failed_rate(
    rows: list[dict[str, Any]], window_hours: int, label: str
) -> QualityFailedRate:
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    in_window = [
        r for r in rows
        if r.get("started_at") and datetime.fromisoformat(r["started_at"].replace("+00:00", "+00:00")) >= since
    ]
    total = len(in_window)
    failed = sum(1 for r in in_window if r.get("status") == "quality_failed")
    return QualityFailedRate(
        window=label,
        total_runs=total,
        quality_failed=failed,
        failure_rate=round(failed / total, 4) if total else 0.0,
    )


def _fetch_quality_failed_rate(sb: Client) -> list[QualityFailedRate]:
    rows = (
        sb.schema("ops")
        .table("pipeline_runs")
        .select("status,started_at")
        .order("started_at", desc=True)
        .limit(500)
        .execute()
        .data or []
    )
    return [
        _compute_quality_failed_rate(rows, 24, "24h"),
        _compute_quality_failed_rate(rows, 168, "7d"),
    ]


@router.get("", response_model=MetricsResponse)
async def metrics_summary(sb: Client = Depends(get_supabase)) -> MetricsResponse:
    try:
        return MetricsResponse(
            sources_volume_7d=_fetch_sources_volume_7d(sb),
            last_success_by_flow=_fetch_last_success(sb),
            sentiment_daily=_fetch_sentiment_daily(sb),
            quality_failed_rate=_fetch_quality_failed_rate(sb),
            generated_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc


@router.get("/sources_volume_7d", response_model=list[SourceVolumeDay])
async def sources_volume_7d(sb: Client = Depends(get_supabase)) -> list[SourceVolumeDay]:
    try:
        return _fetch_sources_volume_7d(sb)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc


@router.get("/last_success_by_flow", response_model=list[LastSuccessByFlow])
async def last_success_by_flow(sb: Client = Depends(get_supabase)) -> list[LastSuccessByFlow]:
    try:
        return _fetch_last_success(sb)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc


@router.get("/sentiment_daily", response_model=list[SentimentDay])
async def sentiment_daily(sb: Client = Depends(get_supabase)) -> list[SentimentDay]:
    try:
        return _fetch_sentiment_daily(sb)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc


@router.get("/quality_failed_rate", response_model=list[QualityFailedRate])
async def quality_failed_rate(sb: Client = Depends(get_supabase)) -> list[QualityFailedRate]:
    try:
        return _fetch_quality_failed_rate(sb)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"supabase: {exc}") from exc
