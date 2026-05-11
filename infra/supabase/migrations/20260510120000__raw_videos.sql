-- Migration: raw video metadata tables
-- Tablas paralelas a raw.posts para guardar metadata de videos que los
-- scrapers de YouTube y TikTok recolectan junto a los comentarios.
-- No reemplazan raw.posts; son entidades distintas (videos vs comments).

-- ── 1. raw.youtube_videos ──────────────────────────────────────────────
create table if not exists raw.youtube_videos (
  video_id      text primary key,
  title         text,
  channel       text,
  channel_id    text,
  description   text,
  published_at  timestamptz,
  view_count    bigint,
  like_count    bigint,
  comment_count bigint,
  duration      int,                          -- segundos
  tags          text,                         -- comma-separated
  query         text,
  collected_at  timestamptz,
  ingested_at   timestamptz not null default now(),
  run_id        uuid not null
);

create index if not exists yt_videos_channel_idx
  on raw.youtube_videos (channel_id);

create index if not exists yt_videos_published_idx
  on raw.youtube_videos (published_at desc nulls last);

create index if not exists yt_videos_run_idx
  on raw.youtube_videos (run_id);

comment on table raw.youtube_videos is
  'Metadata de videos de YouTube. Una fila por video. UPSERT por video_id refresca stats en cada corrida.';


-- ── 2. raw.tiktok_videos ───────────────────────────────────────────────
create table if not exists raw.tiktok_videos (
  video_id         text primary key,
  hashtag          text,
  create_time      timestamptz,
  author_unique_id text,
  author_nickname  text,
  description      text,                      -- 'desc' es reservado
  play_count       bigint,
  digg_count       bigint,                    -- likes
  comment_count    bigint,
  share_count      bigint,
  video_duration   int,                       -- segundos
  ingested_at      timestamptz not null default now(),
  run_id           uuid not null
);

create index if not exists tk_videos_hashtag_idx
  on raw.tiktok_videos (hashtag);

create index if not exists tk_videos_author_idx
  on raw.tiktok_videos (author_unique_id);

create index if not exists tk_videos_run_idx
  on raw.tiktok_videos (run_id);

comment on table raw.tiktok_videos is
  'Metadata de videos de TikTok. Una fila por video. UPSERT por video_id refresca stats.';


-- ── 3. RLS: solo service_role escribe / lee ────────────────────────────
alter table raw.youtube_videos enable row level security;
alter table raw.tiktok_videos  enable row level security;

drop policy if exists "service_role full access" on raw.youtube_videos;
create policy "service_role full access"
  on raw.youtube_videos
  as permissive for all to service_role
  using (true) with check (true);

drop policy if exists "service_role full access" on raw.tiktok_videos;
create policy "service_role full access"
  on raw.tiktok_videos
  as permissive for all to service_role
  using (true) with check (true);
