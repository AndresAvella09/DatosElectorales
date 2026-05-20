"""
quality_gate — Stage 3 BLOQUEANTE (§7.4).

Envuelve `data_pipeline.quality.gate.run_gate` en un @flow. El padre
`pipeline_e2e` consulta `report["overall"]` y decide:
    PASS / WARN -> continuar a silver_to_gold
    FAIL        -> finish(status="quality_failed") y no tocar gold
"""

from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger, task

from data_pipeline.quality import gate


@task(
    name="gate.run_gate",
    retries=1,
    retry_delay_seconds=5,
)
def _run_gate_task(run_id: str, layer: str) -> dict[str, Any]:
    # Acceso via attr del modulo para que monkeypatch de tests pueda
    # interceptar (`gate.run_gate = ...`).
    return gate.run_gate(run_id, layer=layer)


@flow(
    name="quality_gate",
    description="5 checks bloqueantes sobre silver.posts; persiste a ops.quality_reports",
)
def quality_gate(run_id: str, layer: str = "silver") -> dict[str, Any]:
    """Devuelve el reporte completo; el caller decide segun report['overall']."""
    log = get_run_logger()
    log.info("quality_gate: run_id=%s layer=%s", run_id[:8], layer)
    report = _run_gate_task(run_id, layer)
    log.info(
        "quality_gate: overall=%s records=%s",
        report.get("overall"),
        report.get("total_records"),
    )
    return report
