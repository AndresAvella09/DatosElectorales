"""
ingest_videos — Flow para CSV de videos (no comments).

Los scrapers de YouTube/TikTok escriben dos CSV por corrida: uno de
comments (que va al pipeline e2e completo) y uno de videos (metadata
del video padre). Este flow solo se encarga del segundo: lo manda a
`raw.{source}_videos` via `loaders.videos.load_csv`.

Existe como @flow para que cada CSV de videos sea visible como un run
independiente en la UI de Prefect, con su task graph propio.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from prefect import flow, get_run_logger, task

from data_pipeline.loaders import runs, videos

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROCESSED_DIR = _PROJECT_ROOT / "data" / "processed"


@task(
    name="videos.load_csv",
    retries=2,
    retry_delay_seconds=10,
)
def _load_videos(csv_path: str, source: str, run_id: str) -> int:
    return videos.load_csv(csv_path, source=source, run_id=run_id)


@task(name="videos.archive")
def _archive(csv_path: str) -> str:
    """Mueve el CSV a data/processed/<date>/."""
    path = Path(csv_path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest_dir = _PROCESSED_DIR / today
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        dest = dest_dir / f"{path.stem}.{stamp}{path.suffix}"
    shutil.move(str(path), str(dest))
    return str(dest)


@flow(
    name="ingest_videos",
    description="CSV de videos -> raw.{source}_videos (no pasa por silver/gold)",
)
def ingest_videos(csv_path: str | Path, source: str) -> dict:
    """
    Carga un CSV de metadata de videos.

    Returns: dict con run_id, status, rows.
    """
    log = get_run_logger()
    csv_path = str(csv_path)

    if source not in ("youtube", "tiktok"):
        # Solo youtube/tiktok tienen tabla de videos en raw.*.
        log.warning("ingest_videos: source=%s no tiene tabla raw.*_videos", source)
        return {"run_id": None, "status": "skipped", "rows": 0}

    run_id = runs.start("ingest_videos")
    log.info("ingest_videos: csv=%s source=%s run=%s",
             Path(csv_path).name, source, run_id[:8])

    summary: dict = {"run_id": run_id, "status": "running", "rows": 0}
    try:
        n = _load_videos(csv_path, source, run_id)
        summary["rows"] = n
        _archive(csv_path)
        runs.finish(run_id, status="success", rows_out=n)
        summary["status"] = "success"
        log.info("ingest_videos: DONE rows=%d run=%s", n, run_id[:8])
        return summary
    except Exception as exc:
        runs.finish(run_id, status="failed", error=str(exc))
        summary["status"] = "failed"
        log.exception("ingest_videos: FAIL run=%s: %s", run_id[:8], exc)
        raise
