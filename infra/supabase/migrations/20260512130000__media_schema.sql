-- Migration: schema media
-- Datos de monitoreo de medios de comunicación (prensa).
-- Carga directa desde CSVs ya procesados — no pasa por el pipeline bronze/silver.

create schema if not exists media;

-- ── media.mentions ─────────────────────────────────────────────────
-- Una fila por (artículo × candidato). Fuente: mentions.csv

create table if not exists media.mentions (
  article_id   text        not null,
  url          text,
  medio        text        not null,
  fecha        date        not null,
  titulo       text,
  candidato    text        not null,
  menciones    int         not null default 1,
  titulo_flag  boolean     not null default false,
  evento_tipo  text,
  region       text,
  loaded_at    timestamptz not null default now(),
  primary key (article_id, candidato)
);

create index if not exists media_mentions_fecha_idx
  on media.mentions (fecha desc);

create index if not exists media_mentions_candidato_idx
  on media.mentions (candidato, fecha desc);

create index if not exists media_mentions_medio_idx
  on media.mentions (medio, fecha desc);

comment on table media.mentions is
  'Menciones de candidatos en artículos de prensa. PK: (article_id, candidato).';


-- ── media.share_of_voice ───────────────────────────────────────────
-- Una fila por (fecha × medio × candidato).
-- Fusiona share_of_voice.csv y momentum.csv (mismo dataset, columnas extras en momentum).

create table if not exists media.share_of_voice (
  fecha          date        not null,
  medio          text        not null,
  candidato      text        not null,
  menciones      int,
  share_of_voice numeric(8,6),
  rolling_7      numeric(10,4),
  momentum       numeric(10,4),
  loaded_at      timestamptz not null default now(),
  primary key (fecha, medio, candidato)
);

create index if not exists media_sov_candidato_fecha_idx
  on media.share_of_voice (candidato, fecha desc);

create index if not exists media_sov_medio_fecha_idx
  on media.share_of_voice (medio, fecha desc);

comment on table media.share_of_voice is
  'Share of voice y momentum por (fecha, medio, candidato). '
  'rolling_7 y momentum son nullable — vienen del archivo momentum.csv.';


-- ── media.vote_intentions ──────────────────────────────────────────
-- Una fila por (artículo × candidato). Fuente: vote_intentions_clean.csv

create table if not exists media.vote_intentions (
  article_id    text        not null,
  url           text,
  medio         text        not null,
  fecha         date        not null,
  titulo        text,
  candidato     text        not null,
  candidato_raw text,
  porcentaje    numeric(6,2),
  encuestadora  text,
  contexto      text,
  loaded_at     timestamptz not null default now(),
  primary key (article_id, candidato)
);

create index if not exists media_vote_fecha_idx
  on media.vote_intentions (fecha desc);

create index if not exists media_vote_candidato_idx
  on media.vote_intentions (candidato, fecha desc);

comment on table media.vote_intentions is
  'Intenciones de voto extraídas de artículos de prensa. PK: (article_id, candidato).';


-- ── Permisos ───────────────────────────────────────────────────────

grant usage on schema media to service_role;
grant all on all tables in schema media to service_role;
grant usage on schema media to authenticated;
grant select on all tables in schema media to authenticated;
