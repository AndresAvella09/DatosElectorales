"""
silver_to_gold — Stage 4 (§7.5).

Envuelve `gold.promote_run`. Solo se invoca tras quality_gate PASS/WARN.
"""

from __future__ import annotations

from prefect import flow, get_run_logger, task

from data_pipeline.loaders import gold


@task(
    name="gold.promote_run",
    retries=2,
    retry_delay_seconds=10,
)
def _promote_gold(run_id: str) -> int:
    return gold.promote_run(run_id, refresh=False)


@flow(
    name="silver_to_gold",
    description="silver.posts(run_id) -> feature_builder -> gold.features(run_id)",
)
def silver_to_gold(run_id: str) -> int:
    """Devuelve filas escritas en gold.features."""
    log = get_run_logger()
    log.info("silver_to_gold: run_id=%s", run_id[:8])
    n = _promote_gold(run_id)
    log.info("silver_to_gold: gold rows=%d", n)
    return n
