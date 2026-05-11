"""
refresh_views — Stage 5 (§7.6).

REFRESH MATERIALIZED VIEW CONCURRENTLY de las public.v_*. Hoy es no-op
porque falta el RPC en Supabase (ver deuda §18 + gold.refresh_views()).
Lo dejamos como flow para que el grafo del e2e quede completo y A1/A10
puedan completarlo cuando expongan el RPC.
"""

from __future__ import annotations

from prefect import flow, get_run_logger, task

from data_pipeline.loaders import gold


@task(
    name="gold.refresh_views",
    retries=2,
    retry_delay_seconds=15,
)
def _refresh_views_task() -> None:
    gold.refresh_views()


@flow(
    name="refresh_views",
    description="REFRESH MATERIALIZED VIEW CONCURRENTLY public.v_*",
)
def refresh_views() -> None:
    log = get_run_logger()
    log.info("refresh_views: invocando gold.refresh_views() (puede ser no-op)")
    _refresh_views_task()
