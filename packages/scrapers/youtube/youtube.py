"""
youtube.py — YouTube comment + reply + video collector for Colombian electoral discourse.

Outputs (en data/inbox/<source>/<YYYY-MM-DD>/):
    run_<HHMMSS>_comments.csv  -> id, parent_id, date, text, username, likes,
                                  views, video_id, video_title, query, source_type
    run_<HHMMSS>_videos.csv    -> video_id, title, channel, channel_id, description,
                                  published_at, view_count, like_count, comment_count,
                                  duration, tags, query, collected_at

`parent_id` esta vacio para top-level y contiene el id del padre para replies,
asi se reconstruyen hilos downstream.

API key rotation
    Lee toda env var que case con YOUTUBE_API_KEY* (mas la legacy
    YOUTUBE_API_KEY) y rota a la siguiente cuando una pega quotaExceeded /
    rateLimitExceeded, asi una corrida completa puede drenar la cuota
    diaria combinada de todas las keys antes de detenerse.

Salidas adicionales (legacy / opt-in):
    - Si SUPABASE_LEGACY_SYNC=1, hace upsert directo a Supabase en las
      tablas legacy `youtube_comments` y `youtube_videos` (no a raw.*).
      Para el pipeline nuevo (raw.posts), deja los CSV en data/inbox/ y
      corre A2 loaders: `python -m data_pipeline.loaders.cli e2e ...`.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()


# ── Config ────────────────────────────────────────────────────────────


def _load_api_keys() -> list[str]:
    """Recolecta toda env var YOUTUBE_API_KEY*, ordenada por sufijo."""
    keys: list[tuple[int, str]] = []
    for name, val in os.environ.items():
        if not name.startswith("YOUTUBE_API_KEY"):
            continue
        if not val:
            continue
        suffix = name[len("YOUTUBE_API_KEY"):]
        order = int(suffix) if suffix.isdigit() else 0
        keys.append((order, val.strip()))
    keys.sort(key=lambda kv: kv[0])
    seen, out = set(), []
    for _, k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


YOUTUBE_API_KEYS = _load_api_keys()

YOUTUBE_QUERIES = [
    "elecciones Colombia 2026",
    "candidatos presidenciales Colombia",
    "debate presidencial Colombia",
]

# None = paginar hasta agotar (sujeto a hard caps de la API).
YOUTUBE_MAX_VIDEOS_PER_QUERY: int | None = None
YOUTUBE_MAX_COMMENTS_PER_VIDEO: int | None = None
YOUTUBE_MAX_REPLIES_PER_COMMENT: int | None = None

# Solo videos publicados en los ultimos N dias. None = sin filtro.
YOUTUBE_PUBLISHED_WITHIN_DAYS = 60

# ── Output paths (data/inbox/<source>/<YYYY-MM-DD>/) ──────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_INBOX_BASE = Path(os.getenv("INBOX_DIR", _PROJECT_ROOT / "data" / "inbox"))
_TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
_RUN_STAMP = datetime.now(timezone.utc).strftime("%H%M%S")
_OUT_DIR = _INBOX_BASE / "youtube" / _TODAY
_OUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CSV = _OUT_DIR / f"run_{_RUN_STAMP}_comments.csv"
VIDEOS_CSV = _OUT_DIR / f"run_{_RUN_STAMP}_videos.csv"

CSV_FIELDS = [
    "id", "parent_id", "date", "text", "username", "likes",
    "views", "video_id", "video_title", "query", "source_type",
]

VIDEO_CSV_FIELDS = [
    "video_id", "title", "channel", "channel_id", "description",
    "published_at", "view_count", "like_count", "comment_count",
    "duration", "tags", "query", "collected_at",
]

QUOTA_REASONS = {
    "quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded",
    "userRateLimitExceeded",
}

# Legacy Supabase upsert (tablas planas tiktok_*/youtube_*). Apagado por
# defecto: el pipeline canonico es CSV -> data/inbox -> A2 loaders -> raw.*
LEGACY_SUPABASE_SYNC = os.getenv("SUPABASE_LEGACY_SYNC", "0") == "1"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_COMMENTS_TABLE = "youtube_comments"
SUPABASE_VIDEOS_TABLE = "youtube_videos"
SUPABASE_BATCH = 500


# ── API key rotation ──────────────────────────────────────────────────


class YouTubeRotator:
    """Wraps a googleapiclient youtube client and rotates keys on quota."""

    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("No YOUTUBE_API_KEY* found in .env")
        self.keys = keys
        self.idx = 0
        self.exhausted: set[int] = set()
        self.yt = self._build()

    def _build(self):
        return build(
            "youtube", "v3", developerKey=self.keys[self.idx],
            cache_discovery=False,
        )

    def _rotate(self) -> bool:
        self.exhausted.add(self.idx)
        if len(self.exhausted) >= len(self.keys):
            return False
        nxt = (self.idx + 1) % len(self.keys)
        while nxt in self.exhausted:
            nxt = (nxt + 1) % len(self.keys)
        print(
            f"    [YouTube] Key #{self.idx + 1} exhausted -> switching to "
            f"key #{nxt + 1}"
        )
        self.idx = nxt
        self.yt = self._build()
        return True

    @staticmethod
    def _is_quota(err: HttpError) -> bool:
        if err.resp.status != 403:
            return False
        try:
            reason = err.error_details[0].get("reason", "")  # type: ignore[attr-defined]
        except Exception:
            reason = ""
        if reason in QUOTA_REASONS:
            return True
        msg = str(err).lower()
        return "quota" in msg or "ratelimit" in msg

    def execute(self, request_fn):
        """Call request_fn(yt) -> request, .execute() it, rotate on quota."""
        while True:
            try:
                return request_fn(self.yt).execute()
            except HttpError as e:
                if self._is_quota(e):
                    if self._rotate():
                        continue
                    raise RuntimeError(
                        "All YouTube API keys exhausted") from e
                raise


# ── Helpers ───────────────────────────────────────────────────────────


def _row(id_, parent_id, date, text, username, likes, views,
         video_id, video_title, query):
    return {
        "id":          str(id_),
        "parent_id":   str(parent_id) if parent_id else "",
        "date":        date,
        "text":        (text or "").strip(),
        "username":    username,
        "likes":       int(likes),
        "views":       int(views),
        "video_id":    video_id,
        "video_title": (video_title or "").strip(),
        "query":       query,
    }


def _load_existing_ids(path: Path | str, key: str = "id") -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    ids = set()
    with open(p, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = row.get(key)
            if v:
                ids.add(v)
    return ids


_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _iso_duration_to_seconds(iso: str) -> int:
    if not iso:
        return 0
    m = _DUR_RE.fullmatch(iso)
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


# ── Search & video metadata ───────────────────────────────────────────


def _search_videos(rot: YouTubeRotator, query: str) -> list[dict]:
    """Pagina search.list, hidrata metadata via videos.list (50 a la vez)."""
    base_kwargs = dict(
        q=query,
        part="snippet",
        type="video",
        maxResults=50,
        relevanceLanguage="es",
        regionCode="CO",
        order="date" if YOUTUBE_PUBLISHED_WITHIN_DAYS else "relevance",
    )
    if YOUTUBE_PUBLISHED_WITHIN_DAYS:
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=YOUTUBE_PUBLISHED_WITHIN_DAYS)
        base_kwargs["publishedAfter"] = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    video_ids: list[str] = []
    page_token = None
    while True:
        kwargs = dict(base_kwargs)
        if page_token:
            kwargs["pageToken"] = page_token
        resp = rot.execute(lambda yt, k=kwargs: yt.search().list(**k))
        for item in resp.get("items", []):
            vid = item["id"].get("videoId")
            if vid:
                video_ids.append(vid)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        if (YOUTUBE_MAX_VIDEOS_PER_QUERY is not None
                and len(video_ids) >= YOUTUBE_MAX_VIDEOS_PER_QUERY):
            break

    if YOUTUBE_MAX_VIDEOS_PER_QUERY is not None:
        video_ids = video_ids[:YOUTUBE_MAX_VIDEOS_PER_QUERY]
    if not video_ids:
        return []

    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    videos: list[dict] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        stats_resp = rot.execute(lambda yt, ids=",".join(batch): yt.videos().list(
            id=ids, part="statistics,snippet,contentDetails",
        ))
        for item in stats_resp.get("items", []):
            sn = item["snippet"]
            st = item.get("statistics", {})
            cd = item.get("contentDetails", {})
            duration_iso = cd.get("duration", "")
            videos.append({
                "video_id":      item["id"],
                "title":         sn.get("title", ""),
                "channel":       sn.get("channelTitle", ""),
                "channel_id":    sn.get("channelId", ""),
                "description":   sn.get("description", ""),
                "published_at":  sn.get("publishedAt", ""),
                "view_count":    int(st.get("viewCount", 0)),
                "like_count":    int(st.get("likeCount", 0)),
                "comment_count": int(st.get("commentCount", 0)),
                "duration":      _iso_duration_to_seconds(duration_iso),
                "tags":          ", ".join(sn.get("tags", []) or []),
                "query":         query,
                "collected_at":  collected_at,
            })
    return videos


# ── Comments / replies ────────────────────────────────────────────────


def _fetch_replies(rot: YouTubeRotator, parent_id: str, video: dict,
                   query: str) -> list[dict]:
    """Pagina toda reply de un comentario top-level."""
    replies: list[dict] = []
    page_token = None

    while True:
        if (YOUTUBE_MAX_REPLIES_PER_COMMENT is not None
                and len(replies) >= YOUTUBE_MAX_REPLIES_PER_COMMENT):
            break
        try:
            resp = rot.execute(lambda yt, pt=page_token: yt.comments().list(
                parentId=parent_id, part="snippet", maxResults=100,
                textFormat="plainText", pageToken=pt,
            ))
        except HttpError as e:
            if e.resp.status in (403, 404):
                return replies
            raise

        for item in resp.get("items", []):
            c = item["snippet"]
            replies.append(_row(
                id_         = f"yt_{item['id']}",
                parent_id   = f"yt_{parent_id}",
                date        = c["publishedAt"].replace("T", " ").replace("Z", ""),
                text        = c["textDisplay"],
                username    = c["authorDisplayName"],
                likes       = c.get("likeCount", 0),
                views       = video["view_count"],
                video_id    = video["video_id"],
                video_title = video["title"],
                query       = query,
            ))

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    if YOUTUBE_MAX_REPLIES_PER_COMMENT is not None:
        replies = replies[:YOUTUBE_MAX_REPLIES_PER_COMMENT]
    return replies


def _get_comments(rot: YouTubeRotator, video: dict, query: str) -> list[dict]:
    """Pagina todo comentario top-level + replies de un video."""
    rows: list[dict] = []
    page_token = None
    top_level_count = 0

    while True:
        if (YOUTUBE_MAX_COMMENTS_PER_VIDEO is not None
                and top_level_count >= YOUTUBE_MAX_COMMENTS_PER_VIDEO):
            break
        try:
            resp = rot.execute(lambda yt, pt=page_token: yt.commentThreads().list(
                videoId=video["video_id"], part="snippet,replies",
                maxResults=100, textFormat="plainText", order="time",
                pageToken=pt,
            ))
        except HttpError as e:
            if e.resp.status in (403, 404):
                # 403 = comentarios deshabilitados.
                return rows
            raise

        for item in resp.get("items", []):
            top = item["snippet"]["topLevelComment"]
            top_id = top["id"]
            c = top["snippet"]
            total_replies = item["snippet"].get("totalReplyCount", 0)

            rows.append(_row(
                id_         = f"yt_{top_id}",
                parent_id   = "",
                date        = c["publishedAt"].replace("T", " ").replace("Z", ""),
                text        = c["textDisplay"],
                username    = c["authorDisplayName"],
                likes       = c.get("likeCount", 0),
                views       = video["view_count"],
                video_id    = video["video_id"],
                video_title = video["title"],
                query       = query,
            ))
            top_level_count += 1

            if total_replies == 0:
                continue

            inline = item.get("replies", {}).get("comments", [])
            if (inline and total_replies <= len(inline)
                    and YOUTUBE_MAX_REPLIES_PER_COMMENT is None):
                for r in inline:
                    rc = r["snippet"]
                    rows.append(_row(
                        id_         = f"yt_{r['id']}",
                        parent_id   = f"yt_{top_id}",
                        date        = rc["publishedAt"].replace("T", " ").replace("Z", ""),
                        text        = rc["textDisplay"],
                        username    = rc["authorDisplayName"],
                        likes       = rc.get("likeCount", 0),
                        views       = video["view_count"],
                        video_id    = video["video_id"],
                        video_title = video["title"],
                        query       = query,
                    ))
            else:
                rows.extend(_fetch_replies(rot, top_id, video, query))

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return rows


# ── Top-level orchestration ───────────────────────────────────────────


def _phase1_search_videos(rot: YouTubeRotator) -> list[dict]:
    """Corre cada query, dedupea por video_id dentro de este run."""
    seen_vids: set[str] = set()
    found: list[dict] = []
    for query in YOUTUBE_QUERIES:
        try:
            videos = _search_videos(rot, query)
        except HttpError as e:
            print(f"  [YouTube] Search failed ({query!r}): {e}")
            continue
        except RuntimeError as e:
            print(f"  [YouTube] {e}")
            break

        new_in_query = 0
        for v in videos:
            if v["video_id"] in seen_vids:
                continue
            seen_vids.add(v["video_id"])
            found.append(v)
            new_in_query += 1
        print(
            f"    [YouTube] search {query!r}: {len(videos)} videos returned, "
            f"{new_in_query} unique this run"
        )
    return found


def _phase2_collect_comments(rot: YouTubeRotator, videos: list[dict],
                             existing_ids: set[str],
                             on_video_done=None) -> list[dict]:
    """Itera videos, pagina comentarios + replies."""
    seen = set(existing_ids)
    all_new_rows: list[dict] = []

    for i, video in enumerate(videos, start=1):
        try:
            rows = _get_comments(rot, video, video.get("query", ""))
        except RuntimeError as e:
            print(f"  [YouTube] {e}")
            break

        new_rows = [r for r in rows if r["id"] not in seen]
        seen.update(r["id"] for r in new_rows)
        all_new_rows.extend(new_rows)

        n_top = sum(1 for r in new_rows if not r["parent_id"])
        n_rep = sum(1 for r in new_rows if r["parent_id"])
        print(
            f"    [YouTube] [{i}/{len(videos)}] "
            f"{video['video_id']} - {len(rows)} fetched "
            f"({n_top} new comments, {n_rep} new replies) - "
            f"{video['title'][:60]!r}"
        )

        if on_video_done is not None:
            on_video_done(video, rows, new_rows)

        time.sleep(0.05)

    return all_new_rows


def collect(existing_ids: set[str] | None = None,
            existing_video_ids: set[str] | None = None,
            ) -> tuple[list[dict], list[dict]]:
    """Two-phase: search & store videos primero, despues comentarios."""
    if not YOUTUBE_API_KEYS:
        print("  [YouTube] Skipped - no YOUTUBE_API_KEY* set in .env")
        return [], []

    print(f"  [YouTube] Loaded {len(YOUTUBE_API_KEYS)} API key(s) for rotation")
    rot = YouTubeRotator(YOUTUBE_API_KEYS)

    seen_videos = existing_video_ids or set()

    print("  [YouTube] Phase 1/2 - searching videos...")
    videos = _phase1_search_videos(rot)
    print(
        f"  [YouTube] Phase 1 done - {len(videos)} videos in window "
        f"({sum(1 for v in videos if v['video_id'] not in seen_videos)} new)"
    )

    if videos:
        if LEGACY_SUPABASE_SYNC:
            upload_videos_to_supabase(videos)
        new_videos_for_csv = [v for v in videos
                              if v["video_id"] not in seen_videos]
        if new_videos_for_csv:
            save_videos(new_videos_for_csv)

    print("  [YouTube] Phase 2/2 - fetching all comments per video...")

    def _persist(_video, all_rows, new_rows):
        if all_rows and LEGACY_SUPABASE_SYNC:
            upload_to_supabase(all_rows)
        if new_rows:
            save(new_rows)

    comments = _phase2_collect_comments(
        rot, videos, existing_ids or set(), on_video_done=_persist)

    return comments, videos


# ── Persistence ───────────────────────────────────────────────────────


def _save_csv(rows: list[dict], path: Path | str, fields: list[str], label: str) -> None:
    if not rows:
        print(f"  No {label} to save.")
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    file_exists = p.exists() and p.stat().st_size > 0
    with open(p, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved {len(rows)} {label} -> {p}")


def save(posts: list[dict], path: Path | str = OUTPUT_CSV) -> None:
    _save_csv(posts, path, CSV_FIELDS, "comment rows")


def save_videos(videos: list[dict], path: Path | str = VIDEOS_CSV) -> None:
    _save_csv(videos, path, VIDEO_CSV_FIELDS, "video rows")


def _supabase_client():
    """Cliente legacy para tablas planas. Se importa solo si hace falta."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("  [Supabase] Skipped - SUPABASE_URL/SUPABASE_KEY no set")
        return None
    try:
        from supabase import create_client  # noqa: PLC0415
    except ImportError:
        print("  [Supabase] supabase-py no instalado; salteando legacy sync")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upload_to_supabase(posts: list[dict]) -> None:
    if not posts:
        return
    client = _supabase_client()
    if client is None:
        return
    rows = [{**p, "parent_id": p["parent_id"] or None} for p in posts]
    for i in range(0, len(rows), SUPABASE_BATCH):
        chunk = rows[i:i + SUPABASE_BATCH]
        client.table(SUPABASE_COMMENTS_TABLE).upsert(
            chunk, on_conflict="id").execute()
    print(f"  Uploaded {len(rows)} rows -> Supabase.{SUPABASE_COMMENTS_TABLE}")


def upload_videos_to_supabase(videos: list[dict]) -> None:
    if not videos:
        return
    client = _supabase_client()
    if client is None:
        return
    rows = [{k: v.get(k) for k in VIDEO_CSV_FIELDS} for v in videos]
    for i in range(0, len(rows), SUPABASE_BATCH):
        chunk = rows[i:i + SUPABASE_BATCH]
        client.table(SUPABASE_VIDEOS_TABLE).upsert(
            chunk, on_conflict="video_id").execute()
    print(f"  Uploaded {len(rows)} rows -> Supabase.{SUPABASE_VIDEOS_TABLE}")


if __name__ == "__main__":
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"Collecting from YouTube..."
    )
    print(f"  Output dir: {_OUT_DIR}")
    print(f"  Comments CSV: {OUTPUT_CSV.name}")
    print(f"  Videos CSV:   {VIDEOS_CSV.name}")
    if LEGACY_SUPABASE_SYNC:
        print("  Legacy Supabase sync: ENABLED (youtube_comments / youtube_videos)")
    else:
        print(
            "  Legacy Supabase sync: disabled. Use A2 loaders to send these "
            "CSVs to raw.posts: python -m data_pipeline.loaders.cli e2e --csv "
            "<file> --source youtube"
        )

    existing = _load_existing_ids(OUTPUT_CSV, key="id")
    existing_videos = _load_existing_ids(VIDEOS_CSV, key="video_id")
    print(
        f"  {len(existing)} comment ids already in {OUTPUT_CSV.name} - "
        f"will be skipped"
    )
    print(
        f"  {len(existing_videos)} video ids already in {VIDEOS_CSV.name} - "
        f"will be skipped"
    )

    posts, videos = collect(
        existing_ids=existing, existing_video_ids=existing_videos)
    print(
        f"-> {len(posts)} new comment/reply rows, {len(videos)} new videos "
        f"(already persisted incrementally)"
    )
