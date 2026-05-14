"""
Unified hashtag + comment scraper.

Phase 1 – fetch videos from a hashtag, append new ones to VIDEOS_CSV.
Phase 2 – for every video, drain all comments, skipping already-seen IDs,
           append new ones to COMMENTS_CSV.

Re-run safe: existing rows are never overwritten; only new data is appended.
New comments that appeared on already-processed videos are picked up because
the script always scans from the first page and skips known comment IDs.

ms_token is refreshed automatically every TOKEN_REFRESH_INTERVAL seconds by
reading the msToken cookie from your real Chrome/Firefox session (no new
window). If that fails, Playwright fetches it silently.
"""

import asyncio
import csv
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Asegurar que TikTokApi (vendored) y supabase_sync (al lado) sean importables
# sin importar desde donde se invoque el script.
_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from TikTokApi import TikTokApi  # noqa: E402
from TikTokApi.exceptions import EmptyResponseException, InvalidResponseException  # noqa: E402

# Buscar el .env desde la raiz del repo (3 niveles arriba: scrapers -> packages -> repo).
_REPO_ROOT = _PKG_ROOT.parents[2]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()  # tambien intenta el CWD para compat

# ── Legacy Supabase sync (tablas planas tiktok_videos / tiktok_comments) ────
# Apagado por defecto. El pipeline canonico es: CSV en data/inbox/ + A2 loaders
# que escriben a raw.posts. Activar con SUPABASE_LEGACY_SYNC=1 si quieres
# mantener las tablas legacy.
SUPABASE_SYNC = os.environ.get("SUPABASE_LEGACY_SYNC", "0") == "1"
try:
    if SUPABASE_SYNC:
        from supabase_sync import comment_uploader, video_uploader  # type: ignore
    else:
        comment_uploader = video_uploader = None  # type: ignore
except Exception as _exc:  # noqa: BLE001
    print(f"[supabase] legacy sync disabled - import failed: {_exc}")
    SUPABASE_SYNC = False
    comment_uploader = video_uploader = None  # type: ignore

# ── Output paths (data/inbox/tiktok/<YYYY-MM-DD>/) ────────────────────────────
_INBOX_BASE = Path(os.getenv("INBOX_DIR", _REPO_ROOT / "data" / "inbox"))
_TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
_RUN_STAMP = datetime.now(timezone.utc).strftime("%H%M%S")
_OUT_DIR = _INBOX_BASE / "tiktok" / _TODAY
_OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── configuration ─────────────────────────────────────────────────────────────
hashtag_name = os.environ.get("HASHTAG", "eleccionescolombia2026")
videos_csv   = os.environ.get("VIDEOS_CSV",   str(_OUT_DIR / f"run_{_RUN_STAMP}_videos.csv"))
comments_csv = os.environ.get("COMMENTS_CSV", str(_OUT_DIR / f"run_{_RUN_STAMP}_comments.csv"))

VIDEO_COUNT = int(os.environ.get("VIDEO_COUNT", "60"))
MAX_NEW_COMMENTS_PER_VIDEO = 1000   # stop after this many *new* comments
MAX_SCAN_PER_VIDEO = 1500          # hard ceiling on total comments iterated
SKIP_KNOWN_VIDEOS = os.environ.get("SKIP_KNOWN_VIDEOS", "0") == "1"
SLEEP_BETWEEN_VIDEOS  = (15, 30)  # seconds, randomised
BACKOFF_BASE = 30                  # seconds, doubles on each retry
MAX_RETRIES  = 3
TOKEN_REFRESH_INTERVAL = 30 * 60   # refresh ms_token every 30 minutes
BROWSER  = os.getenv("TIKTOK_BROWSER", "chromium")
HEADLESS = os.environ.get("TIKTOK_HEADLESS", "false").lower() == "true"
# ──────────────────────────────────────────────────────────────────────────────


# ── token helpers ─────────────────────────────────────────────────────────────

def _token_from_browser() -> str | None:
    """Read msToken from the real Chrome or Firefox cookie store (no new window)."""
    try:
        import browser_cookie3
        for loader in (browser_cookie3.chrome, browser_cookie3.firefox):
            try:
                jar = loader(domain_name=".tiktok.com")
                token = next((c.value for c in jar if c.name == "msToken"), None)
                if token:
                    print(f"  [token] read from {'Chrome' if loader is browser_cookie3.chrome else 'Firefox'}")
                    return token
            except Exception:
                continue
    except ImportError:
        pass
    return None


async def _token_from_playwright() -> str | None:
    """Open TikTok with a headless Playwright browser, grab msToken, close."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto("https://www.tiktok.com", timeout=30_000)
            await asyncio.sleep(5)  # let JS set the cookie
            cookies = await ctx.cookies("https://www.tiktok.com")
            token = next((c["value"] for c in cookies if c["name"] == "msToken"), None)
            await browser.close()
            if token:
                print("  [token] fetched via Playwright")
            return token
    except Exception as exc:
        print(f"  [token] Playwright fallback failed: {exc}")
        return None


async def get_ms_token() -> str | None:
    """Return a fresh msToken, trying the real browser first."""
    token = _token_from_browser()
    if not token:
        token = await _token_from_playwright()
    if not token:
        print("  [token] WARNING: could not obtain ms_token automatically.")
    return token
# ──────────────────────────────────────────────────────────────────────────────


def load_seen_ids(filepath: str, id_column: str) -> set:
    """Return a set of all values in *id_column* from an existing CSV."""
    seen = set()
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return seen
    with open(filepath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            val = row.get(id_column)
            if val:
                seen.add(val)
    return seen


def open_csv_writer(filepath: str, headers: list):
    """
    Open *filepath* in append mode.
    Write the header row only when the file is new / empty.
    Returns (file_handle, csv.writer).
    """
    is_new = not os.path.exists(filepath) or os.path.getsize(filepath) == 0
    fh = open(filepath, "a", newline="", encoding="utf-8")
    writer = csv.writer(fh)
    if is_new:
        writer.writerow(headers)
    return fh, writer


# DOM selectors TikTok uses for its captcha overlay. We try several plus
# a body-HTML substring sniff and an iframe-URL check, because TikTok
# rotates classnames and sometimes renders the captcha inside an iframe.
CAPTCHA_SELECTORS = (
    "#captcha-verify-image",
    ".captcha_verify_container",
    "div[class*='captcha']",
    "div[id*='captcha']",
    "iframe[src*='captcha']",
    "iframe[src*='verify']",
)
CAPTCHA_HTML_HINTS = (
    "captcha-verify-image",
    "captcha_verify",
    "verify_bar_title",
    "verify-bar",
    "secsdk-captcha",
)


async def captcha_visible(page) -> bool:
    # 1. selector-based check on the main frame
    for sel in CAPTCHA_SELECTORS:
        try:
            if await page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    # 2. iframe URL check — TikTok captcha is often served in a child frame
    try:
        for frame in page.frames:
            url = (frame.url or "").lower()
            if "captcha" in url or "verify" in url:
                return True
    except Exception:
        pass
    # 3. body HTML substring sniff — last resort, catches rotated classnames
    try:
        html = (await page.content()).lower()
        if any(hint in html for hint in CAPTCHA_HTML_HINTS):
            return True
    except Exception:
        pass
    return False


async def wait_until_captcha_cleared(page, max_wait: int = 600) -> None:
    """
    If a captcha is visible, prompt the human and poll until it's gone
    (or max_wait seconds elapse).
    """
    if not await captcha_visible(page):
        return
    print("\n  [captcha] detected — solve it in the Playwright window.")
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        await asyncio.sleep(2)
        if not await captcha_visible(page):
            print("  [captcha] cleared, continuing.")
            await asyncio.sleep(random.uniform(2, 4))
            return
    print("  [captcha] timed out waiting; continuing anyway.")


async def warm_video_page(api, video_id: str, author_unique_id: str | None) -> None:
    """
    Navigate the Playwright tab to the actual video page so TikTok rotates
    cookies and the session looks like a real viewer before we hit the
    comment-list endpoint. If a captcha appears, wait for the human.
    """
    if not api.sessions:
        return
    page = api.sessions[0].page
    if author_unique_id:
        url = f"https://www.tiktok.com/@{author_unique_id}/video/{video_id}"
    else:
        url = f"https://www.tiktok.com/video/{video_id}"
    try:
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(3, 6))  # let JS settle, cookies rotate
        await wait_until_captcha_cleared(page)
    except Exception as exc:
        print(f"  [warm] {url} → {exc}")


async def wait_for_captcha_clear(api) -> None:
    """If a captcha is showing on the session's page, wait for the human."""
    if api.sessions:
        await wait_until_captcha_cleared(api.sessions[0].page)


async def reset_session(api, ms_token: str) -> None:
    """Tear down all sessions and create a fresh one with the current token."""
    print("  [session] recreating browser session …")
    try:
        await api.close_sessions()
    except Exception as exc:
        print(f"  [session] close warning: {exc}")
    await api.create_sessions(
        ms_tokens=[ms_token],
        num_sessions=1,
        sleep_after=6,
        browser=BROWSER,
        headless=HEADLESS,
    )
    await wait_for_captcha_clear(api)


async def drain_comments(api, video_id: str, author_unique_id: str | None, writer, seen_ids: set, sb_uploader=None) -> int:
    """
    Iterate comments for *video_id*, writing rows that are not in *seen_ids*.

    Stops when EITHER:
      * MAX_NEW_COMMENTS_PER_VIDEO new comments have been written, OR
      * MAX_SCAN_PER_VIDEO total comments have been iterated (hard ceiling
        to prevent runaway pagination on heavily-known videos), OR
      * the API runs out of pages.

    Returns the number of newly written comments.
    """
    await warm_video_page(api, video_id, author_unique_id)
    video_obj = api.video(id=video_id)
    new_count = 0
    scanned   = 0

    async for comment in video_obj.comments(count=MAX_SCAN_PER_VIDEO):
        scanned += 1
        d   = comment.as_dict
        cid = str(d.get("cid", ""))

        if not cid or cid in seen_ids:
            continue  # already stored – keep paginating until we find new ones

        seen_ids.add(cid)

        ts = d.get("create_time")
        created_at = (
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if ts else ""
        )
        row = [
            video_id,
            cid,
            created_at,
            (d.get("user") or {}).get("unique_id"),
            (d.get("user") or {}).get("nickname"),
            d.get("text"),
            d.get("digg_count"),
            d.get("reply_comment_total"),
        ]
        writer.writerow(row)
        if sb_uploader is not None:
            sb_uploader.add({
                "video_id":       row[0],
                "comment_id":     row[1],
                "create_time":    row[2] or None,
                "user_unique_id": row[3],
                "user_nickname":  row[4],
                "text":           row[5],
                "digg_count":     row[6],
                "reply_count":    row[7],
            })
        new_count += 1

        if new_count >= MAX_NEW_COMMENTS_PER_VIDEO:
            break

    if scanned >= MAX_SCAN_PER_VIDEO and new_count < MAX_NEW_COMMENTS_PER_VIDEO:
        print(f"  [scan-cap] hit {MAX_SCAN_PER_VIDEO}-comment ceiling without "
              f"finding {MAX_NEW_COMMENTS_PER_VIDEO} new — moving on.")
    return new_count


async def run():
    seen_video_ids   = load_seen_ids(videos_csv,   "video_id")
    seen_comment_ids = load_seen_ids(comments_csv, "comment_id")
    print(f"Resuming: {len(seen_video_ids)} known videos, {len(seen_comment_ids)} known comments.\n")

    # Live Supabase mirror — None when SUPABASE_SYNC=0 or import failed.
    sb_videos   = video_uploader()   if SUPABASE_SYNC and video_uploader   else None
    sb_comments = comment_uploader() if SUPABASE_SYNC and comment_uploader else None
    if sb_videos is None:
        print("[supabase] live sync disabled.\n")
    else:
        print("[supabase] live sync enabled — rows will be upserted in batches.\n")

    # get initial token (env var wins; fall back to auto-detect)
    ms_token = os.environ.get("ms_token") or await get_ms_token()
    last_token_refresh = time.monotonic()

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=6,
            browser=BROWSER,
            headless=HEADLESS,
        )
        await wait_for_captcha_clear(api)

        # ── Phase 1: collect hashtag videos ───────────────────────────────────
        print(f"[Phase 1] Fetching up to {VIDEO_COUNT} videos for #{hashtag_name} …")
        new_videos:   list[tuple[str, str | None]] = []
        known_videos: list[tuple[str, str | None]] = []

        vfh, vwriter = open_csv_writer(videos_csv, [
            "hashtag", "video_id", "create_time", "author_unique_id",
            "author_nickname", "desc", "play_count", "digg_count",
            "comment_count", "share_count", "video_duration",
        ])
        try:
            tag = api.hashtag(name=hashtag_name)
            async for video in tag.videos(count=VIDEO_COUNT):
                d   = video.as_dict
                vid = str(d.get("id", ""))
                if not vid:
                    continue
                author = d.get("author") or {}
                entry  = (vid, author.get("uniqueId"))

                if vid in seen_video_ids:
                    known_videos.append(entry)
                    print(f"  [known]  {vid}")
                    continue

                new_videos.append(entry)
                seen_video_ids.add(vid)
                stats  = d.get("stats")  or {}
                ts     = d.get("createTime")
                created_at = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    if ts else ""
                )
                vrow = [
                    hashtag_name, vid, created_at,
                    author.get("uniqueId"), author.get("nickname"),
                    d.get("desc"),
                    stats.get("playCount"), stats.get("diggCount"),
                    stats.get("commentCount"), stats.get("shareCount"),
                    (d.get("video") or {}).get("duration"),
                ]
                vwriter.writerow(vrow)
                vfh.flush()
                if sb_videos is not None:
                    sb_videos.add({
                        "hashtag":          vrow[0],
                        "video_id":         vrow[1],
                        "create_time":      vrow[2] or None,
                        "author_unique_id": vrow[3],
                        "author_nickname":  vrow[4],
                        "desc":             vrow[5],
                        "play_count":       vrow[6],
                        "digg_count":       vrow[7],
                        "comment_count":    vrow[8],
                        "share_count":      vrow[9],
                        "video_duration":   vrow[10],
                    })
                print(f"  [new]    {vid}  {d.get('desc', '')[:70]}")
        finally:
            vfh.close()
            # Flush so the videos table is up-to-date BEFORE comments start
            # streaming (comments FK-reference video_id).
            if sb_videos is not None:
                sb_videos.flush()

        # New videos first so they get scraped even if the run is cut short.
        # Known videos are revisited only to look for *additional* new comments.
        if SKIP_KNOWN_VIDEOS:
            video_queue = new_videos
            print(f"\nSKIP_KNOWN_VIDEOS=1 → skipping {len(known_videos)} known videos.")
        else:
            video_queue = new_videos + known_videos

        print(f"\n{len(video_queue)} videos queued ({len(new_videos)} new, "
              f"{len(known_videos) if not SKIP_KNOWN_VIDEOS else 0} revisits).\n")

        # ── Phase 2: drain comments for every video ────────────────────────────
        print("[Phase 2] Scraping comments …")
        cfh, cwriter = open_csv_writer(comments_csv, [
            "video_id", "comment_id", "create_time", "user_unique_id",
            "user_nickname", "text", "digg_count", "reply_count",
        ])
        try:
            for idx, (vid, author_uid) in enumerate(video_queue, 1):
                # refresh token every TOKEN_REFRESH_INTERVAL seconds
                if time.monotonic() - last_token_refresh >= TOKEN_REFRESH_INTERVAL:
                    print("\n[token] refreshing ms_token …")
                    new_token = await get_ms_token()
                    if new_token:
                        ms_token = new_token
                        await reset_session(api, ms_token)
                    last_token_refresh = time.monotonic()

                print(f"\n[{idx}/{len(video_queue)}] video {vid}")

                backoff = BACKOFF_BASE
                success = False
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        new = await drain_comments(api, vid, author_uid, cwriter, seen_comment_ids, sb_comments)
                        cfh.flush()
                        print(f"  → {new} new comments written.")
                        success = True
                        break
                    except (EmptyResponseException, InvalidResponseException) as exc:
                        print(f"  [attempt {attempt}/{MAX_RETRIES}] error: {exc}")
                        if attempt < MAX_RETRIES:
                            # First, see if a captcha is on screen — if so, just wait
                            # for the human and retry without rebuilding the session.
                            page = api.sessions[0].page if api.sessions else None
                            if page and await captcha_visible(page):
                                await wait_until_captcha_cleared(page)
                            else:
                                # Truly burned session: refresh token + recreate browser
                                new_token = await get_ms_token()
                                if new_token:
                                    ms_token = new_token
                                    last_token_refresh = time.monotonic()
                                await reset_session(api, ms_token)
                                print(f"  Backing off {backoff}s …")
                                await asyncio.sleep(backoff)
                                backoff *= 2
                        else:
                            print(f"  Giving up on video {vid}.")

                if success and idx < len(video_queue):
                    delay = random.uniform(*SLEEP_BETWEEN_VIDEOS)
                    print(f"  Sleeping {delay:.1f}s before next video …")
                    await asyncio.sleep(delay)
        finally:
            cfh.close()
            if sb_comments is not None:
                sb_comments.flush()
            if sb_videos is not None:
                sb_videos.flush()

    print("\nAll done.")


if __name__ == "__main__":
    asyncio.run(run())
