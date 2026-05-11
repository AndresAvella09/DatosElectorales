-- Migration: gold.features
-- Gold: features listas para consumo + slots ML (sentiment_*) que el equipo
-- de modelos rellena fuera de este pipeline.

create table if not exists gold.features (
  id                  text primary key,
  source              text not null check (source in ('twitter','youtube','facebook','tiktok','other')),
  datetime_utc        timestamptz,
  word_count          int,
  char_count          int,
  has_hashtags        boolean,
  has_emojis          boolean,
  has_urls_original   boolean,
  hour_of_day         int,
  day_of_week         int,
  days_until_election int,
  engagement          jsonb not null default '{}'::jsonb,
  engagement_score    numeric,

  -- Slots reservados para ML (los rellena el equipo de modelos).
  sentiment_label     text,
  sentiment_score     numeric,
  candidate_mentioned text,

  enriched_at         timestamptz not null default now(),
  run_id              uuid not null
);

create index if not exists gold_features_source_dt_idx
  on gold.features (source, datetime_utc desc);

create index if not exists gold_features_run_id_idx
  on gold.features (run_id);

create index if not exists gold_features_sentiment_idx
  on gold.features (sentiment_label)
  where sentiment_label is not null;

comment on table gold.features is
  'Gold: 1 fila por post enriquecido. sentiment_* lo escribe el equipo ML asincronamente.';
