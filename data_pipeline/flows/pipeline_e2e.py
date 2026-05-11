"""
pipeline_e2e — Flow padre que encadena bronze -> silver -> gate -> gold -> refresh.

Es el dueno de `ops.pipeline_runs`: crea el run_id con `runs.start("e2e")`,
lo propaga a los sub-flows, y lo cierra con el status final:
    success         -> todo OK, gold y views actualizados
    quality_failed  -> gate retorno FAIL; gold no se toco
    failed          -> excepcion no controlada en alguna etapa

Idempotencia: lo garantizan los loaders (sha256 en bronze, UPSERT por id
en silver/gold). Reintentar el e2e con el mismo CSV no duplica.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, get_run_logger, task

from data_pipeline.flows.bronze_to_silver import bronze_to_silver
from data_pipeline.flows.quality_gate import quality_gate
from data_pipeline.flows.refresh_views import refresh_views
from data_pipeline.flows.silver_to_gold import silver_to_gold
from data_pipeline.loaders import bronze, runs


@task(
    name="bronze.load_csv",
    retries=2,
    retry_delay_seconds=10,
)
def _load_bronze(csv_path: str, source: str, run_id: str, skip_storage: bool) -> int:
    return bronze.load_csv(
        csv_path,
        source=source,
        run_id=run_id,
        skip_storage=skip_storage,
        archive=True,
    )


@flow(
    name="pipeline_e2e",
    description="CSV -> bronze -> silver -> quality gate -> [gold opcional] -> refresh",
)
def pipeline_e2e(
    csv_path: str | Path,
    source: str,
    *,
    skip_storage: bool = True,
    skip_gold: bool = True,
) -> dict:
    """
    Procesa un CSV de inbox a traves del pipeline.

    Args:
        csv_path:     CSV de entrada (en data/inbox/).
        source:       twitter | youtube | tiktok | external.
        skip_storage: True = no sube CSV al bucket bronze-raw (ahorra plan free).
        skip_gold:    True = se detiene tras Quality Gate; no toca gold.features
                      ni refresca views. Default True mientras el equipo de ML
                      termina las features de gold.

    Returns:
        dict con: run_id, status, rows_bronze, rows_silver, rows_gold,
                  quality_overall.
    """
    log = get_run_logger()
    csv_path = str(csv_path)

    flow_name = "e2e_silver_only" if skip_gold else "e2e"
    run_id = runs.start(flow_name)
    log.info("pipeline_e2e: csv=%s source=%s run=%s skip_gold=%s",
             Path(csv_path).name, source, run_id[:8], skip_gold)

    summary: dict = {
        "run_id": run_id,
        "status": "running",
        "rows_bronze": 0,
        "rows_silver": 0,
        "rows_gold": 0,
        "quality_overall": None,
    }

    try:
        # Bronze
        n_bronze = _load_bronze(csv_path, source, run_id, skip_storage)
        summary["rows_bronze"] = n_bronze
        if n_bronze == 0:
            # CSV vacio, duplicado por sha, o sin posts validos. Cerramos OK.
            runs.finish(run_id, status="success", rows_out=0)
            summary["status"] = "success"
            log.info("pipeline_e2e: bronze=0 (vacio o duplicado); fin temprano")
            return summary

        # Silver
        n_silver = bronze_to_silver(run_id)
        summary["rows_silver"] = n_silver
        if n_silver == 0:
            # Todo lo que vino ya estaba en silver. No hay nada nuevo que evaluar.
            runs.finish(run_id, status="success", rows_out=0)
            summary["status"] = "success"
            log.info("pipeline_e2e: silver=0 (todo duplicado); fin temprano")
            return summary

        # Quality Gate (bloqueante)
        report = quality_gate(run_id, layer="silver")
        overall = report.get("overall")
        summary["quality_overall"] = overall

        if overall == "FAIL":
            runs.finish(
                run_id,
                status="quality_failed",
                rows_out=0,
                quality_summary={
                    "overall": overall,
                    "total_records": report.get("total_records"),
                },
            )
            summary["status"] = "quality_failed"
            log.warning("pipeline_e2e: gate=FAIL -> gold/silver-final no se toca")
            return summary

        # Modo silver-only: cerrar como exito tras gate PASS/WARN.
        if skip_gold:
            runs.finish(
                run_id,
                status="success",
                rows_out=n_silver,
                quality_summary={"overall": overall},
            )
            summary["status"] = "success"
            log.info(
                "pipeline_e2e: DONE (silver-only) bronze=%d silver=%d gate=%s",
                n_bronze, n_silver, overall,
            )
            return summary

        # Gold (PASS o WARN)
        n_gold = silver_to_gold(run_id)
        summary["rows_gold"] = n_gold

        # Refresh views (no-op por ahora; cuando A1 exponga el RPC sera real)
        refresh_views()

        runs.finish(
            run_id,
            status="success",
            rows_out=n_gold,
            quality_summary={"overall": overall},
        )
        summary["status"] = "success"
        log.info(
            "pipeline_e2e: DONE bronze=%d silver=%d gold=%d gate=%s",
            n_bronze, n_silver, n_gold, overall,
        )
        return summary

    except Exception as exc:
        runs.finish(run_id, status="failed", error=str(exc))
        summary["status"] = "failed"
        log.exception("pipeline_e2e: FAIL run=%s: %s", run_id[:8], exc)
        raise
