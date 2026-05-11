"""
bronze_to_silver — Promueve raw.posts(run_id) a silver.posts.

Stage 2 del pipeline (§7.3). Envuelve `silver.promote_run` en un @flow
de Prefect para que sea visible en la UI y participe en el grafo de
dependencias del e2e.

No abre fila propia en ops.pipeline_runs: el padre `pipeline_e2e` es
el dueno del run_id.
"""

from __future__ import annotations

from prefect import flow, get_run_logger, task

from data_pipeline.loaders import silver


@task(
    name="silver.promote_run",
    retries=2,
    retry_delay_seconds=10,
)
def _promote_silver(run_id: str) -> int:
    return silver.promote_run(run_id)


@flow(
    name="bronze_to_silver",
    description="raw.posts(run_id) -> cleaner -> anonymizer -> silver.posts(run_id)",
)
def bronze_to_silver(run_id: str) -> int:
    """Devuelve filas escritas en silver.posts (solo nuevas)."""
    log = get_run_logger()
    log.info("bronze_to_silver: run_id=%s", run_id[:8])
    n = _promote_silver(run_id)
    log.info("bronze_to_silver: silver rows=%d", n)
    return n
