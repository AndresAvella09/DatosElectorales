"""
Supabase sync helper for the TikTok scraper.

Reads SUPABASE_URL and SUPABASE_KEY from .env.

Two ways to use it:

1. Bulk: `upload_csv_videos(path)` / `upload_csv_comments(path)` to push an
   existing CSV in chunked upserts.
2. Streaming: `BatchedUploader("tiktok_videos", "video_id")` — call
   `.add(row)` after each row you write to your CSV; the uploader buffers
   and flushes every BATCH_SIZE rows. Call `.flush()` at the end of the run.

Conflict policy: upsert on the primary key (video_id / comment_id), so re-runs
update existing rows instead of erroring.
"""

from __future__ import annotations

import csv
import os
from typing import Iterable

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

VIDEOS_TABLE   = "tiktok_videos"
COMMENTS_TABLE = "tiktok_comments"

VIDEO_PK   = "video_id"
COMMENT_PK = "comment_id"

# Columns that should be cast to int when present (CSV gives us strings).
_INT_VIDEO_COLS   = {"play_count", "digg_count", "comment_count", "share_count", "video_duration"}
_INT_COMMENT_COLS = {"digg_count", "reply_count"}

BATCH_SIZE = 50           # streaming flush threshold
BULK_CHUNK = 500          # per-request size for the one-shot uploader


_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        _client = create_client(url, key)
    return _client


def _coerce_row(row: dict, int_cols: set[str]) -> dict:
    """Convert CSV string values to ints / None where appropriate."""
    out: dict = {}
    for k, v in row.items():
        if v is None or v == "":
            out[k] = None
        elif k in int_cols:
            try:
                out[k] = int(float(v))
            except (TypeError, ValueError):
                out[k] = None
        else:
            out[k] = v
    return out


def _upsert(table: str, pk: str, rows: list[dict]) -> None:
    if not rows:
        return
    get_client().table(table).upsert(rows, on_conflict=pk).execute()


# ── Streaming uploader ────────────────────────────────────────────────────────

class BatchedUploader:
    """
    Buffer rows in memory and upsert when the buffer reaches BATCH_SIZE.
    Use one instance per table.
    """

    def __init__(self, table: str, pk: str, int_cols: set[str], batch_size: int = BATCH_SIZE):
        self.table = table
        self.pk = pk
        self.int_cols = int_cols
        self.batch_size = batch_size
        self._buf: list[dict] = []

    def add(self, row: dict) -> None:
        self._buf.append(_coerce_row(row, self.int_cols))
        if len(self._buf) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buf:
            return
        try:
            _upsert(self.table, self.pk, self._buf)
            print(f"  [supabase] upserted {len(self._buf)} → {self.table}")
        except Exception as exc:
            # Don't crash the scraper on a transient upload error; the next
            # full-CSV bulk upload will reconcile.
            print(f"  [supabase] WARN flush failed for {self.table}: {exc}")
        finally:
            self._buf.clear()


def video_uploader() -> BatchedUploader:
    return BatchedUploader(VIDEOS_TABLE, VIDEO_PK, _INT_VIDEO_COLS)


def comment_uploader() -> BatchedUploader:
    return BatchedUploader(COMMENTS_TABLE, COMMENT_PK, _INT_COMMENT_COLS)


# ── Bulk CSV uploader ─────────────────────────────────────────────────────────

def _stream_csv(path: str, int_cols: set[str]) -> Iterable[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield _coerce_row(row, int_cols)


def _upload_csv(path: str, table: str, pk: str, int_cols: set[str]) -> int:
    if not os.path.exists(path):
        print(f"[supabase] skip: {path} does not exist")
        return 0

    chunk: list[dict] = []
    total = 0
    for row in _stream_csv(path, int_cols):
        chunk.append(row)
        if len(chunk) >= BULK_CHUNK:
            _upsert(table, pk, chunk)
            total += len(chunk)
            print(f"  [supabase] {table}: {total} rows uploaded so far …")
            chunk.clear()
    if chunk:
        _upsert(table, pk, chunk)
        total += len(chunk)
    print(f"[supabase] {table}: {total} rows total.")
    return total


def upload_csv_videos(path: str = "tiktok_videos.csv") -> int:
    return _upload_csv(path, VIDEOS_TABLE, VIDEO_PK, _INT_VIDEO_COLS)


def upload_csv_comments(path: str = "tiktok_comments.csv") -> int:
    return _upload_csv(path, COMMENTS_TABLE, COMMENT_PK, _INT_COMMENT_COLS)
