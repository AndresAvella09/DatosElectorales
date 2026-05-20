"""
models.py — Modelos Pydantic de respuesta para la API.

Mantienen el contrato hacia el front estable independientemente de
cambios menores en las vistas SQL. Solo se exponen campos necesarios.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RunStatus = Literal["running", "success", "failed", "quality_failed"]
QualityOverall = Literal["PASS", "WARN", "FAIL"]
QualityLayer = Literal["silver", "gold"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    timestamp: datetime
    environment: str
    supabase_reachable: bool
    detail: str | None = None


class PipelineRun(BaseModel):
    run_id: str
    flow_name: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    rows_in: int | None = None
    rows_out: int | None = None
    quality_summary: dict[str, Any] | None = None
    error: str | None = None


class RunsList(BaseModel):
    items: list[PipelineRun]
    count: int


class QualityReport(BaseModel):
    run_id: str
    layer: QualityLayer
    overall: QualityOverall
    checks: list[dict[str, Any]]
    created_at: datetime


class QualityList(BaseModel):
    items: list[QualityReport]
    count: int


class SourceVolumeDay(BaseModel):
    source: str
    posts: int


class LastSuccessByFlow(BaseModel):
    flow_name: str
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    rows_out: int | None = None


class SentimentDay(BaseModel):
    source: str
    posts: int
    positive_count: int | None = None
    negative_count: int | None = None
    neutral_count: int | None = None
    avg_sentiment: float | None = None


class QualityFailedRate(BaseModel):
    window: Literal["24h", "7d"]
    total_runs: int
    quality_failed: int
    failure_rate: float


class MetricsResponse(BaseModel):
    sources_volume_7d: list[SourceVolumeDay]
    last_success_by_flow: list[LastSuccessByFlow]
    sentiment_daily: list[SentimentDay]
    quality_failed_rate: list[QualityFailedRate]
    generated_at: datetime
