"""
tiktok_anonymize.py — Anonimización y deduplicación de los CSVs crudos de TikTok.

Lee los CSVs de ingesta (bronze), aplica:
  1. Eliminación de columnas de nombre (author_nickname, user_nickname).
  2. Hash SHA-256 sobre los IDs de usuario (author_unique_id, user_unique_id)
     reutilizando hash_username() del módulo silver.anonymizer.
  3. Deduplicación por clave primaria (video_id / comment_id),
     conservando la primera ocurrencia.

Escribe los resultados en una carpeta de salida configurable.

Uso:
    python data_pipeline/quality/tiktok_anonymize.py
    python data_pipeline/quality/tiktok_anonymize.py \\
        --videos tiktok_videos.csv \\
        --comments tiktok_comments.csv \\
        --out data_pipeline/quality/output
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_PROJECT_ROOT  = Path(__file__).resolve().parents[2]   # repo root
_PIPELINE_ROOT = Path(__file__).resolve().parents[1]   # data_pipeline/
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PIPELINE_ROOT))

from silver.anonymizer import hash_username  # noqa: E402

# ── column config ─────────────────────────────────────────────────────────────

_VIDEOS_DROP   = {"author_nickname"}
_COMMENTS_DROP = {"user_nickname"}

_VIDEOS_HASH_COLS   = {"author_unique_id"}
_COMMENTS_HASH_COLS = {"user_unique_id"}

_VIDEO_PK   = "video_id"
_COMMENT_PK = "comment_id"


# ── core helpers ──────────────────────────────────────────────────────────────

def _process(
    src: Path,
    dst: Path,
    pk: str,
    drop_cols: set[str],
    hash_cols: set[str],
) -> tuple[int, int, int]:
    """
    Read *src* CSV, anonymize, deduplicate, write to *dst*.

    Returns (total_read, duplicates_removed, rows_written).
    """
    if not src.exists():
        print(f"[skip] {src} does not exist.")
        return 0, 0, 0

    rows: list[dict] = []
    with src.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    total_read = len(rows)

    # 1. Drop nickname columns
    for row in rows:
        for col in drop_cols:
            row.pop(col, None)

    # 2. Hash user-ID columns
    for row in rows:
        for col in hash_cols:
            if col in row:
                row[col] = hash_username(row[col]) if row[col] else None

    # 3. Deduplicate by pk (keep first occurrence)
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        pk_val = row.get(pk, "")
        if pk_val and pk_val in seen:
            continue
        if pk_val:
            seen.add(pk_val)
        deduped.append(row)

    duplicates = total_read - len(deduped)

    # 4. Write output
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not deduped:
        print(f"[warn] {src.name}: no rows to write after processing.")
        return total_read, duplicates, 0

    fieldnames = list(deduped[0].keys())
    with dst.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deduped)

    return total_read, duplicates, len(deduped)


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Anonymize and deduplicate TikTok CSVs.")
    parser.add_argument("--videos",   default="tiktok_videos.csv",   help="Raw videos CSV path")
    parser.add_argument("--comments", default="tiktok_comments.csv", help="Raw comments CSV path")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).parent / "output"),
        help="Output directory for clean CSVs",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)

    datasets = [
        (
            Path(args.videos),
            out_dir / "tiktok_videos_clean.csv",
            _VIDEO_PK,
            _VIDEOS_DROP,
            _VIDEOS_HASH_COLS,
            "videos",
        ),
        (
            Path(args.comments),
            out_dir / "tiktok_comments_clean.csv",
            _COMMENT_PK,
            _COMMENTS_DROP,
            _COMMENTS_HASH_COLS,
            "comments",
        ),
    ]

    for src, dst, pk, drop, hash_cols, label in datasets:
        total, dupes, written = _process(src, dst, pk, drop, hash_cols)
        if total:
            print(
                f"[{label}] read={total}  duplicates_removed={dupes}  written={written}"
                f"  → {dst}"
            )


if __name__ == "__main__":
    main()
