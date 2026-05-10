"""
runs.py — Helpers para escribir en ops.pipeline_runs.

Cada flow del pipeline llama a `start(...)` al inicio y `finish(...)` al
final. La fila intermedia con status='running' permite ver flows en vuelo
desde public.v_pipeline_health.

Uso:
    from data_pipeline.loaders import runs

    run_id = runs.start("bronze_to_silver", rows_in=320)
    try:
        ... trabajo ...
        runs.finish(run_id, status="success", rows_out=318)
    except Exception as e:
        runs.finish(run_id, status="failed", error=str(e))
        raise
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from logger import get_logger  # noqa: E402

from data_pipeline.loaders._client import get_client  # noqa: E402

log = get_logger("loaders.runs")


VALID_STATUS = {"running", "success", "failed", "quality_failed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def start(flow_name: str, rows_in: int | None = None) -> str:
    """
    Crea una fila en ops.pipeline_runs con status='running'.

    Returns:
        run_id (uuid string) — usalo en todos los UPSERTs de este run.
    """
    run_id = str(uuid.uuid4())
    sb = get_client()
    sb.schema("ops").table("pipeline_runs").insert(
        {
            "run_id": run_id,
            "flow_name": flow_name,
            "status": "running",
            "started_at": _now_iso(),
            "rows_in": rows_in,
        }
    ).execute()
    log.info("[run %s] start flow=%s rows_in=%s", run_id[:8], flow_name, rows_in)
    return run_id


def finish(
    run_id: str,
    status: str,
    rows_out: int | None = None,
    quality_summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Cierra una corrida actualizando finished_at y status."""
    if status not in VALID_STATUS:
        raise ValueError(f"status invalido: {status}. Valido: {VALID_STATUS}")

    payload: dict[str, Any] = {
        "status": status,
        "finished_at": _now_iso(),
    }
    if rows_out is not None:
        payload["rows_out"] = rows_out
    if quality_summary is not None:
        payload["quality_summary"] = quality_summary
    if error is not None:
        payload["error"] = error[:2000]  # truncar por si acaso

    sb = get_client()
    sb.schema("ops").table("pipeline_runs").update(payload).eq("run_id", run_id).execute()
    log.info(
        "[run %s] finish status=%s rows_out=%s",
        run_id[:8],
        status,
        rows_out,
    )
