"""
gate.py — Quality Gate orquestado contra Supabase.

Lee `silver.posts` de un `run_id` dado, calcula el baseline de volumen
con los ultimos 7 runs success, corre los 5 checks de `checks.py` y
persiste el resultado en `ops.quality_reports` + actualiza
`ops.pipeline_runs.quality_summary`.

API publica:
    run_gate(run_id, *, layer="silver") -> dict
        Devuelve el reporte con clave "overall" in {"PASS","WARN","FAIL"}.
        El caller decide si abortar (FAIL) o continuar (PASS/WARN).
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts.silver import CleanPost  # noqa: E402
from logger import get_logger  # noqa: E402

from data_pipeline.loaders._client import get_client  # noqa: E402
from data_pipeline.quality.checks import run_quality_gate  # noqa: E402

log = get_logger("quality.gate")

SELECT_PAGE = 1000
BASELINE_RUNS = 7


def _fetch_silver_for_run(run_id: str) -> list[CleanPost]:
    """Lee silver.posts WHERE run_id=$1 y materializa CleanPost."""
    sb = get_client()
    posts: list[CleanPost] = []
    offset = 0
    while True:
        res = (
            sb.schema("silver")
            .table("posts")
            .select(
                "id, source, source_id, datetime_utc, username_hash, "
                "text_clean, text_original, parent_id, engagement, metadata, "
                "lang, pii_detected, pii_types, is_duplicate, cleaned_at"
            )
            .eq("run_id", run_id)
            .range(offset, offset + SELECT_PAGE - 1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            break
        for row in rows:
            try:
                posts.append(CleanPost(**row))
            except Exception as exc:  # noqa: BLE001
                log.warning("gate: silver.posts.id=%s no parsea: %s",
                            row.get("id"), exc)
        if len(rows) < SELECT_PAGE:
            break
        offset += SELECT_PAGE
    return posts


def _fetch_volume_baseline(exclude_run_id: str, limit: int = BASELINE_RUNS) -> list[int]:
    """
    Devuelve `rows_out` de los ultimos N runs success de flows e2e/ingest.

    Usa ops.pipeline_runs para que cualquier flujo que ingiera (e2e, watcher)
    contribuya al baseline. Excluye el run actual y los que sean None.
    """
    sb = get_client()
    res = (
        sb.schema("ops")
        .table("pipeline_runs")
        .select("rows_out")
        .eq("status", "success")
        .neq("run_id", exclude_run_id)
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [r["rows_out"] for r in (res.data or []) if r.get("rows_out")]


def _persist_report(run_id: str, layer: str, report: dict) -> None:
    """Inserta en ops.quality_reports (idempotente via PK compuesta)."""
    sb = get_client()
    payload = {
        "run_id": run_id,
        "layer": layer,
        "overall": report["overall"],
        "checks": report["checks"],
    }
    # PK = (run_id, layer). Si ya existe, sobrescribimos via upsert.
    sb.schema("ops").table("quality_reports").upsert(
        payload, on_conflict="run_id,layer"
    ).execute()


def _update_run_summary(run_id: str, summary: dict) -> None:
    """Pone el resumen del gate en ops.pipeline_runs.quality_summary."""
    sb = get_client()
    sb.schema("ops").table("pipeline_runs").update(
        {"quality_summary": summary}
    ).eq("run_id", run_id).execute()


# ── API publica ────────────────────────────────────────────────────


def run_gate(run_id: str, *, layer: str = "silver") -> dict:
    """
    Ejecuta el quality gate contra silver.posts(run_id) y persiste.

    Returns:
        dict con keys: overall, checks, total_records, timestamp.
        El caller decide segun report["overall"]:
            "PASS" / "WARN" -> continuar a gold
            "FAIL"          -> abortar, runs.finish(status="quality_failed")
    """
    posts = _fetch_silver_for_run(run_id)
    if not posts:
        report = {
            "overall": "FAIL",
            "total_records": 0,
            "checks": [{"check": "completeness", "status": "FAIL",
                        "reason": "silver_empty_for_run"}],
            "reason": "silver_empty_for_run",
        }
        _persist_report(run_id, layer, report)
        _update_run_summary(run_id, _summary_from_report(report))
        log.warning("[gate %s] silver vacio - FAIL automatico", run_id[:8])
        return report

    baseline = _fetch_volume_baseline(exclude_run_id=run_id)
    report = run_quality_gate(posts, prior_volumes=baseline)

    _persist_report(run_id, layer, report)
    _update_run_summary(run_id, _summary_from_report(report))

    log.info(
        "[gate %s] overall=%s records=%d baseline_runs=%d",
        run_id[:8], report["overall"], report["total_records"], len(baseline),
    )
    return report


def _summary_from_report(report: dict) -> dict:
    """Resumen compacto que cabe bien en ops.pipeline_runs.quality_summary."""
    by_check = {
        c["check"]: c["status"]
        for c in report.get("checks", [])
        if isinstance(c, dict) and "check" in c
    }
    return {
        "overall": report.get("overall"),
        "total_records": report.get("total_records"),
        "checks": by_check,
    }
