-- Migration: raw.posts_parlamentarias + silver.posts_parlamentarias
-- Misma estructura que raw.posts / silver.posts pero para datos de
-- elecciones parlamentarias (2022). Tablas separadas para no mezclar
-- contextos electorales en los mismos índices / vistas.

-- ── raw.posts_parlamentarias ──────────────────────────────────────

create table if not exists raw.posts_parlamentarias (
  id            text primary key,
  source        text not null check (source in ('twitter','youtube','facebook','tiktok','other')),
  source_id     text not null,
  storage_path  text not null,
  ingested_at   timestamptz not null default now(),
  run_id        uuid not null,
  raw_payload   jsonb,
  source_sha256 text
);

create index if not exists raw_parl_source_ingested_idx
  on raw.posts_parlamentarias (source, ingested_at desc);

create index if not exists raw_parl_run_id_idx
  on raw.posts_parlamentarias (run_id);

create index if not exists raw_parl_source_sha_idx
  on raw.posts_parlamentarias (source_sha256)
  where source_sha256 is not null;

comment on table raw.posts_parlamentarias is
  'Bronze: posts crudos de elecciones parlamentarias 2022.';

-- ── silver.posts_parlamentarias ───────────────────────────────────
-- Tabla plana (sin particionado): dataset historico fijo, volumen bajo.

create table if not exists silver.posts_parlamentarias (
  id            text not null,
  source        text not null check (source in ('twitter','youtube','facebook','tiktok','other')),
  source_id     text not null,
  datetime_utc  timestamptz,
  author_id     text,
  text_clean    text not null,
  text_original text,
  parent_id     text,
  engagement    jsonb not null default '{}'::jsonb,
  metadata      jsonb not null default '{}'::jsonb,
  lang          text,
  pii_detected  boolean not null default false,
  pii_types     text[]  not null default '{}',
  is_duplicate  boolean not null default false,
  cleaned_at    timestamptz not null default now(),
  run_id        uuid not null,
  primary key (id, cleaned_at)
);

create index if not exists silver_parl_source_dt_idx
  on silver.posts_parlamentarias (source, datetime_utc desc);

create index if not exists silver_parl_run_id_idx
  on silver.posts_parlamentarias (run_id);

create index if not exists silver_parl_lang_idx
  on silver.posts_parlamentarias (lang)
  where lang is not null;

comment on table silver.posts_parlamentarias is
  'Silver: posts parlamentarios limpios y anonimizados.';
