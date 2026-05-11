"""
cli.py — Invocacion manual de los loaders.

Subcomandos:
    bronze    Carga un CSV a raw.posts (+ Storage).
    silver    Promueve un run de raw a silver.
    gold      Promueve un run de silver a gold.
    e2e       bronze -> silver -> gold para un CSV en un solo run_id.
    scan      Lista CSVs pendientes en data/inbox/.

Uso:
    uv run python -m data_pipeline.loaders.cli e2e \\
        --csv data/inbox/twitter/2026-05-10/run_120000.csv \\
        --source twitter

    uv run python -m data_pipeline.loaders.cli silver --run-id <uuid>

    uv run python -m data_pipeline.loaders.cli scan
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from logger import get_logger  # noqa: E402

from data_pipeline.loaders import bronze, gold, runs, silver, videos  # noqa: E402

log = get_logger("loaders.cli")


def _cmd_bronze(args: argparse.Namespace) -> int:
    run_id = runs.start("ingest_inbox")
    try:
        n = bronze.load_csv(
            args.csv,
            source=args.source,
            run_id=run_id,
            skip_storage=not args.upload_to_storage,
            archive=not args.no_archive,
        )
        runs.finish(run_id, status="success", rows_out=n)
        print(f"OK run_id={run_id} rows={n}")
        return 0
    except Exception as exc:  # noqa: BLE001
        runs.finish(run_id, status="failed", error=str(exc))
        log.error("Bronze fallo: %s", exc)
        return 1


def _cmd_silver(args: argparse.Namespace) -> int:
    run_id = args.run_id
    log.info("Promoviendo run=%s a silver", run_id[:8])
    n = silver.promote_run(run_id)
    print(f"OK silver rows={n} run_id={run_id}")
    return 0


def _cmd_gold(args: argparse.Namespace) -> int:
    run_id = args.run_id
    log.info("Promoviendo run=%s a gold", run_id[:8])
    n = gold.promote_run(run_id, refresh=args.refresh)
    print(f"OK gold rows={n} run_id={run_id}")
    return 0


def _cmd_e2e(args: argparse.Namespace) -> int:
    """Bronze + Silver + Gold con el mismo run_id."""
    run_id = runs.start("e2e_manual")
    try:
        n_bronze = bronze.load_csv(
            args.csv,
            source=args.source,
            run_id=run_id,
            skip_storage=not args.upload_to_storage,
            archive=not args.no_archive,
        )
        if n_bronze == 0:
            runs.finish(run_id, status="success", rows_out=0)
            print(f"OK e2e run_id={run_id} (0 filas - posible duplicado por sha)")
            return 0
        n_silver = silver.promote_run(run_id)
        n_gold = gold.promote_run(run_id, refresh=args.refresh)
        runs.finish(run_id, status="success", rows_out=n_gold)
        print(
            f"OK e2e run_id={run_id} bronze={n_bronze} "
            f"silver={n_silver} gold={n_gold}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        runs.finish(run_id, status="failed", error=str(exc))
        log.exception("E2E fallo en run=%s", run_id[:8])
        return 1


def _cmd_videos(args: argparse.Namespace) -> int:
    """Subir un *_videos.csv a raw.{source}_videos."""
    run_id = args.run_id or runs.start("ingest_videos")
    own_run = args.run_id is None
    try:
        n = videos.load_csv(args.csv, source=args.source, run_id=run_id)
        if own_run:
            runs.finish(run_id, status="success", rows_out=n)
        print(f"OK videos rows={n} run_id={run_id}")
        return 0
    except Exception as exc:  # noqa: BLE001
        if own_run:
            runs.finish(run_id, status="failed", error=str(exc))
        log.exception("Videos load fallo: %s", exc)
        return 1


def _cmd_scan(args: argparse.Namespace) -> int:
    pending = bronze.scan_inbox(args.inbox)
    if not pending:
        print(f"(vacio) {args.inbox}")
        return 0
    for path, source in pending:
        print(f"{source}\t{path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="data_pipeline.loaders.cli",
        description="Carga manual de CSVs a Bronze/Silver/Gold en Supabase.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_bronze = sub.add_parser("bronze", help="Subir CSV a raw.posts")
    p_bronze.add_argument("--csv", required=True)
    p_bronze.add_argument("--source", required=True,
                          choices=["twitter", "youtube", "tiktok", "external"])
    p_bronze.add_argument("--upload-to-storage", action="store_true",
                          help="Subir el CSV crudo al bucket bronze-raw "
                               "(off por default para ahorrar espacio)")
    p_bronze.add_argument("--no-archive", action="store_true",
                          help="No mover el CSV a data/processed/")
    p_bronze.set_defaults(func=_cmd_bronze)

    p_silver = sub.add_parser("silver", help="Promover run raw -> silver")
    p_silver.add_argument("--run-id", required=True)
    p_silver.set_defaults(func=_cmd_silver)

    p_gold = sub.add_parser("gold", help="Promover run silver -> gold")
    p_gold.add_argument("--run-id", required=True)
    p_gold.add_argument("--refresh", action="store_true",
                        help="REFRESH matviews tras escribir gold")
    p_gold.set_defaults(func=_cmd_gold)

    p_e2e = sub.add_parser("e2e", help="bronze + silver + gold en un solo run")
    p_e2e.add_argument("--csv", required=True)
    p_e2e.add_argument("--source", required=True,
                       choices=["twitter", "youtube", "tiktok", "external"])
    p_e2e.add_argument("--upload-to-storage", action="store_true",
                       help="Subir el CSV crudo al bucket bronze-raw "
                            "(off por default)")
    p_e2e.add_argument("--no-archive", action="store_true")
    p_e2e.add_argument("--refresh", action="store_true")
    p_e2e.set_defaults(func=_cmd_e2e)

    p_videos = sub.add_parser("videos", help="Subir *_videos.csv a raw.{source}_videos")
    p_videos.add_argument("--csv", required=True)
    p_videos.add_argument("--source", required=True, choices=["youtube", "tiktok"])
    p_videos.add_argument("--run-id", default=None,
                          help="Reusar run_id existente (default: crear uno nuevo)")
    p_videos.set_defaults(func=_cmd_videos)

    p_scan = sub.add_parser("scan", help="Listar CSVs pendientes en data/inbox/")
    p_scan.add_argument("--inbox", default=str(_PROJECT_ROOT / "data" / "inbox"))
    p_scan.set_defaults(func=_cmd_scan)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
