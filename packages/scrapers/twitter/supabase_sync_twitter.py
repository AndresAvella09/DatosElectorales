"""
Supabase sync helper for the X/Twitter scraper.

Reads SUPABASE_URL and SUPABASE_ANON_KEY from .env.

Two ingestion paths share this module:

  PATH A – Automatic (scraper-driven)
  ─────────────────────────────────────
  Set SUPABASE_LEGACY_SYNC=1 in your .env before running twitterScrape.py.
  The scraper will call upload_csv_x(path) automatically when it finishes.

  PATH B – Manual (CSV-drop)
  ───────────────────────────
  Run this file directly against any existing CSV:

      python supabase_sync_twitter.py tweets_colombia.csv
      python supabase_sync_twitter.py --csv data/tweets.csv --chunk 250

  Useful for historical data already collected before the scraper had
  Supabase integration, or for re-syncing after a partial failure.

  PATH C – Streaming (future / advanced)
  ────────────────────────────────────────
  Instantiate tweet_uploader() inside the scraper loop, call .add(row) per
  tweet, and .flush() at the end to upsert in real-time without waiting for
  the full CSV. Not wired into twitterScrape.py yet — reserved for future use.

Conflict policy: upsert on the primary key (id), so re-runs update existing
rows instead of erroring.
"""

from __future__ import annotations

import argparse
import csv
import os
from typing import Iterable

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

# ── Table / column config
X_TABLE = "raw_x_tweets"
X_PK    = "id"

_INT_X_COLS = {"replies", "retweets", "likes"}

BATCH_SIZE = 50
BULK_CHUNK = 500

# ── Singleton client
_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
        
        from supabase import ClientOptions
        schema = os.environ.get("SUPABASE_SCHEMA", "raw")
        opts = ClientOptions(schema=schema)
        
        _client = create_client(url, key, options=opts)
    return _client


# ── Shared helpers ─────────────────────────────────────────────────────────────

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


def _stream_csv(path: str, int_cols: set[str]) -> Iterable[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield _coerce_row(row, int_cols)


# ── PATH C: Streaming uploader (uso futuro)

class BatchedUploader:
    """
    Buffer rows in memory and upsert when the buffer reaches batch_size.
    Use one instance per table.

    Example::

        uploader = tweet_uploader()
        for tweet in scrape():
            uploader.add(tweet)
        uploader.flush()
    """

    def __init__(
        self,
        table: str,
        pk: str,
        int_cols: set[str],
        batch_size: int = BATCH_SIZE,
    ):
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
            # Don't crash the scraper on a transient upload error; a follow-up
            # bulk upload (PATH B) will reconcile.
            print(f"  [supabase] WARN flush failed for {self.table}: {exc}")
        finally:
            self._buf.clear()


def tweet_uploader() -> BatchedUploader:
    """Factory — returns a ready-to-use BatchedUploader for raw_x_tweets."""
    return BatchedUploader(X_TABLE, X_PK, _INT_X_COLS)


# ── PATH A & B: Bulk CSV uploader

def upload_csv_x(path: str = "tweets_colombia.csv", chunk_size: int = BULK_CHUNK) -> int:
    """
    Read *path* and upsert all rows into raw_x_tweets in chunks of *chunk_size*.

    Used by both:
    - PATH A: called automatically by twitterScrape.py after scraping finishes.
    - PATH B: called from __main__ for manual / historical CSV uploads.

    Returns the total number of rows upserted.
    """
    if not os.path.exists(path):
        print(f"[supabase] skip: {path} does not exist")
        return 0

    chunk: list[dict] = []
    total = 0

    for row in _stream_csv(path, _INT_X_COLS):
        # Normalise the Query column name (scraper writes it as "Query")
        if "Query" in row:
            row["query"] = row.pop("Query")

        chunk.append(row)

        if len(chunk) >= chunk_size:
            _upsert(X_TABLE, X_PK, chunk)
            total += len(chunk)
            print(f"  [supabase] {X_TABLE}: {total} rows uploaded so far …")
            chunk.clear()

    if chunk:
        _upsert(X_TABLE, X_PK, chunk)
        total += len(chunk)

    print(f"[supabase] {X_TABLE}: {total} rows total.")
    return total


# ── PATH B entry point ─────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual CSV → Supabase uploader for X/Twitter tweets.",
        epilog="Example: python supabase_sync_twitter.py tweets_colombia.csv --chunk 250",
    )
    parser.add_argument(
        "csv",
        nargs="?",
        default=os.environ.get("CSV_PATH", "tweets_colombia.csv"),
        help='Path to the CSV file to upload (default: from .env CSV_PATH or tweets_colombia.csv)',
    )
    parser.add_argument(
        "--chunk",
        type=int,
        default=BULK_CHUNK,
        help=f"Rows per upsert request (default: {BULK_CHUNK})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    print(f"[supabase] Manual upload: {args.csv}  (chunk={args.chunk})")
    uploaded = upload_csv_x(path=args.csv, chunk_size=args.chunk)
    if uploaded:
        print(f"[supabase] Done — {uploaded} rows upserted into {X_TABLE}.")
    else:
        print("[supabase] Nothing was uploaded. Check the file path and .env credentials.")