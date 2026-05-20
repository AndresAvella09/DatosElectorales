-- Migration: raw.posts
-- Bronze: metadatos del archivo crudo entregado por el scraper.
-- El payload completo vive en Storage (bucket bronze-raw); aqui solo metadatos
-- y una copia minima (raw_payload) para auditoria.

create table if not exists raw.posts (
  id            text primary key,                   -- ej. tw_123, yt_abc
  source        text not null check (source in ('twitter','youtube','facebook','tiktok','other')),
  source_id     text not null,
  storage_path  text not null,                      -- bucket/path en Supabase Storage
  ingested_at   timestamptz not null default now(),
  run_id        uuid not null,
  raw_payload   jsonb,                              -- snapshot minimo para auditoria
  source_sha256 text                                -- hash del archivo origen (idempotencia)
);

create index if not exists raw_posts_source_ingested_idx
  on raw.posts (source, ingested_at desc);

create index if not exists raw_posts_run_id_idx
  on raw.posts (run_id);

create index if not exists raw_posts_source_sha_idx
  on raw.posts (source_sha256)
  where source_sha256 is not null;

comment on table raw.posts is
  'Bronze: 1 fila por post crudo. storage_path apunta al CSV/JSON original en bucket bronze-raw.';
