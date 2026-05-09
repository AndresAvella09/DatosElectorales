# TikTok Scraper — Setup Guide

Scrapes videos and comments for a given hashtag and saves them to CSV files,
with optional live sync to Supabase.

---

## Requirements

- Python 3.11 or newer — [download](https://www.python.org/downloads/)
- Git

---

## 1. Clone the repo

```powershell
git clone <repo-url>
cd Elections
```

---

## 2. Configure environment variables

| Variable          | Description                                                                   |
| ----------------- | ----------------------------------------------------------------------------- |
| `ms_token`      | Your TikTok session token (see below). Leave blank to auto-fetch.             |
| `SUPABASE_URL`  | Your Supabase project URL (e.g.`https://xxxx.supabase.co/`)                 |
| `SUPABASE_KEY`  | Your Supabase**service role** key                                       |
| `HASHTAG`       | Hashtag to scrape (default:`eleccionescolombia2026`)                        |
| `VIDEO_COUNT`   | Max videos to fetch per run (default:`60`)                                  |
| `SUPABASE_SYNC` | Set to `0` to disable Supabase upload and only save to CSV (default: `1`) |

### How to get `ms_token`

1. Open [tiktok.com](https://www.tiktok.com) in Chrome or Firefox and log in.
2. Open DevTools → Application → Cookies → `https://www.tiktok.com`.
3. Find the cookie named `msToken` and copy its value.
4. Paste it as `ms_token=<value>` in your `.env`.

> If you leave `ms_token` blank the scraper will try to read it from your
> browser automatically, and fall back to fetching it via a headless browser.

---

## 3. Run the scraper

From the **repo root** (`Elections/`):

```powershell
.\run_tiktok.ps1
```

Or pass arguments directly (overrides `.env`):

```powershell
.\run_tiktok.ps1 eleccionescolombia2026 60
```

The script will:

1. Create a Python virtual environment inside `tiktok/venv/` (first run only).
2. Install all dependencies automatically.
3. Install the Playwright Chromium browser (first run only).
4. Start scraping — a browser window will open; solve any CAPTCHA if prompted.

---

## 4. Output files

| File                           | Contents                             |
| ------------------------------ | ------------------------------------ |
| `tiktok/tiktok_videos.csv`   | One row per video (metadata + stats) |
| `tiktok/tiktok_comments.csv` | One row per comment                  |

Re-running is safe: existing rows are never overwritten, only new data is appended.

---

## 5. Supabase tables (optional)

If `SUPABASE_SYNC=1`, the scraper upserts rows into these tables:

**`tiktok_videos`**

| Column           | Type      |
| ---------------- | --------- |
| hashtag          | text      |
| video_id         | text (PK) |
| create_time      | timestamp |
| author_unique_id | text      |
| author_nickname  | text      |
| desc             | text      |
| play_count       | int       |
| digg_count       | int       |
| comment_count    | int       |
| share_count      | int       |
| video_duration   | int       |

**`tiktok_comments`**

| Column         | Type      |
| -------------- | --------- |
| video_id       | text (FK) |
| comment_id     | text (PK) |
| create_time    | timestamp |
| user_unique_id | text      |
| user_nickname  | text      |
| text           | text      |
| digg_count     | int       |
| reply_count    | int       |
