"""
videos.py — Loader para raw.youtube_videos y raw.tiktok_videos.

Paralelo a bronze.py pero para metadata de videos (no posts). Los
scrapers de YouTube y TikTok producen dos CSV por corrida:

    run_<HHMMSS>_comments.csv  -> bronze.load_csv (raw.posts)
    run_<HHMMSS>_videos.csv    -> videos.load_csv (raw.{source}_videos)

A diferencia de bronze.py, no sube a Storage ni archiva el CSV (eso lo
hace el watcher tras procesar ambos archivos del run).
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from logger import get_logger  # noqa: E402

from data_pipeline.loaders._client import get_client  # noqa: E402

log = get_logger("loaders.videos")

UPSERT_BATCH = 200


# ── Coercion helpers ──────────────────────────────────────────────────


def _safe_int(v) -> int | None:
    if v is None or str(v).strip() in ("", "nan", "None"):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _safe_ts(v) -> str | None:
    """Acepta ISO 8601 o 'YYYY-MM-DD HH:MM:SS'."""
    if v is None or str(v).strip() in ("", "nan", "None"):
        return None
    s = str(v).strip()
    # YouTube usa "YYYY-MM-DDTHH:MM:SSZ"; TikTok produce "YYYY-MM-DD HH:MM:SS".
    if " " in s and "T" not in s:
        s = s.replace(" ", "T") + "+00:00"
    elif s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        # Validar parseable; devolver ISO normalizado.
        return datetime.fromisoformat(s).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _safe_str(v) -> str | None:
    if v is None:
        return None
    s = str(v)
    return None if s.strip() in ("", "nan", "None") else s


# ── Mapeo por fuente ──────────────────────────────────────────────────


def _yt_row_to_supabase(row: dict, run_id: str) -> dict[str, Any] | None:
    vid = _safe_str(row.get("video_id"))
    if not vid:
        return None
    return {
        "video_id":      vid,
        "title":         _safe_str(row.get("title")),
        "channel":       _safe_str(row.get("channel")),
        "channel_id":    _safe_str(row.get("channel_id")),
        "description":   _safe_str(row.get("description")),
        "published_at":  _safe_ts(row.get("published_at")),
        "view_count":    _safe_int(row.get("view_count")),
        "like_count":    _safe_int(row.get("like_count")),
        "comment_count": _safe_int(row.get("comment_count")),
        "duration":      _safe_int(row.get("duration")),
        "tags":          _safe_str(row.get("tags")),
        "query":         _safe_str(row.get("query")),
        "collected_at":  _safe_ts(row.get("collected_at")),
        "run_id":        run_id,
    }


def _tk_row_to_supabase(row: dict, run_id: str) -> dict[str, Any] | None:
    vid = _safe_str(row.get("video_id"))
    if not vid:
        return None
    return {
        "video_id":         vid,
        "hashtag":          _safe_str(row.get("hashtag")),
        "create_time":      _safe_ts(row.get("create_time")),
        "author_unique_id": _safe_str(row.get("author_unique_id")),
        "author_nickname":  _safe_str(row.get("author_nickname")),
        # CSV column is "desc" (palabra reservada en SQL); la mapeamos a description.
        "description":      _safe_str(row.get("desc") or row.get("description")),
        "play_count":       _safe_int(row.get("play_count")),
        "digg_count":       _safe_int(row.get("digg_count")),
        "comment_count":    _safe_int(row.get("comment_count")),
        "share_count":      _safe_int(row.get("share_count")),
        "video_duration":   _safe_int(row.get("video_duration")),
        "run_id":           run_id,
    }


_MAPPERS = {
    "youtube": (_yt_row_to_supabase, "youtube_videos"),
    "tiktok":  (_tk_row_to_supabase, "tiktok_videos"),
}


def _read_csv(path: Path) -> list[dict]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _upsert_in_batches(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    sb = get_client()
    total = 0
    for i in range(0, len(rows), UPSERT_BATCH):
        chunk = rows[i : i + UPSERT_BATCH]
        sb.schema("raw").table(table).upsert(
            chunk, on_conflict="video_id"
        ).execute()
        total += len(chunk)
        log.debug("raw.%s upsert: %d/%d", table, total, len(rows))
    return total


# ── API publica ───────────────────────────────────────────────────────


def load_csv(
    csv_path: str | Path,
    source: str,
    run_id: str,
) -> int:
    """
    Carga un *_videos.csv a raw.{source}_videos.

    Args:
        csv_path: Ruta al CSV (de scraper youtube/tiktok).
        source:   'youtube' | 'tiktok'.
        run_id:   uuid del run (compartido con el comments load si aplica).

    Returns:
        Numero de filas UPSERTeadas.
    """
    if source not in _MAPPERS:
        raise ValueError(f"source no soportado para videos: {source}")

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV no existe: {path}")

    mapper, table = _MAPPERS[source]

    raw_rows = _read_csv(path)
    log.info("Procesando %s (rows=%d, source=%s, run=%s)",
             path.name, len(raw_rows), source, run_id[:8])

    mapped = []
    skipped = 0
    for row in raw_rows:
        r = mapper(row, run_id)
        if r is None:
            skipped += 1
        else:
            mapped.append(r)

    if skipped:
        log.warning("%d filas sin video_id - skip", skipped)

    written = _upsert_in_batches(table, mapped)
    log.info("raw.%s: %d filas UPSERTeadas (run=%s)",
             table, written, run_id[:8])
    return written
