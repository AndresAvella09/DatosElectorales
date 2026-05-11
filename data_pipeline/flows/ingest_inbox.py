"""
ingest_inbox — Flow cron (§9.1).

Schedule: cada 30 minutos (red de seguridad ademas del watcher en tiempo
real). Escanea data/inbox/<source>/<date>/*.csv y dispara un
`pipeline_e2e` por archivo.

Concurrencia (§9.2): 1 corrida simultanea de este flow. Internamente
procesa los archivos secuencialmente para no saturar Supabase.

Uso programatico (sin Prefect server):
    from data_pipeline.flows.ingest_inbox import ingest_inbox
    ingest_inbox()

Despliegue con cron:
    prefect deploy data_pipeline/flows/ingest_inbox.py:ingest_inbox \\
        --name inbox-cron --cron "*/30 * * * *"
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, get_run_logger

from data_pipeline.flows.pipeline_e2e import pipeline_e2e
from data_pipeline.loaders import bronze

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INBOX = _PROJECT_ROOT / "data" / "inbox"


@flow(
    name="ingest_inbox",
    description="Escaneo periodico de data/inbox/ y dispatch de pipeline_e2e por CSV",
)
def ingest_inbox(inbox_dir: str | Path = DEFAULT_INBOX) -> dict:
    """
    Escanea inbox y procesa cada CSV con pipeline_e2e.

    No ejecuta los archivos en paralelo: los hace en serie para respetar
    el budget de Supabase y para que la fila ops.pipeline_runs sea
    facil de seguir.

    Returns:
        dict con files_scanned y resumen por archivo.
    """
    log = get_run_logger()
    inbox = Path(inbox_dir)

    pending = bronze.scan_inbox(inbox)
    log.info("ingest_inbox: %d archivos en inbox=%s", len(pending), inbox)

    results: list[dict] = []
    for path, source in pending:
        log.info("ingest_inbox: dispatch %s (source=%s)", path.name, source)
        try:
            summary = pipeline_e2e(str(path), source)
        except Exception as exc:  # noqa: BLE001
            # pipeline_e2e ya marca el run como failed; aqui solo logueamos
            # y seguimos con los demas archivos.
            log.exception("ingest_inbox: %s fallo: %s", path.name, exc)
            summary = {"status": "failed", "error": str(exc), "csv": path.name}
        else:
            summary["csv"] = path.name
        results.append(summary)

    return {
        "files_scanned": len(pending),
        "results": results,
    }
