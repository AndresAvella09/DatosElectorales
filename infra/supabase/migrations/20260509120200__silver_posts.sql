-- Migration: silver.posts
-- Silver: posts limpios + anonimizados + dedup + lang detect.
-- Particionado por rango sobre cleaned_at (mensual). Crea particiones futuras
-- segun necesidad con un cron SQL o en el flow refresh_views.

create table if not exists silver.posts (
  id              text not null,
  source          text not null check (source in ('twitter','youtube','facebook','tiktok','other')),
  source_id       text not null,
  datetime_utc    timestamptz,
  username_hash   text,
  text_clean      text not null,
  text_original   text,
  parent_id       text,
  engagement      jsonb not null default '{}'::jsonb,
  metadata        jsonb not null default '{}'::jsonb,
  lang            text,
  pii_detected    boolean not null default false,
  pii_types       text[]  not null default '{}',
  is_duplicate    boolean not null default false,
  cleaned_at      timestamptz not null default now(),
  run_id          uuid not null,
  primary key (id, cleaned_at)
) partition by range (cleaned_at);

-- Particiones iniciales: mes en curso + 2 meses siguientes (idempotente).
do $$
declare
  m  date := date_trunc('month', now())::date;
  n  date;
  i  int;
  pname text;
begin
  for i in 0..2 loop
    n := (m + (i || ' month')::interval)::date;
    pname := 'posts_' || to_char(n, 'YYYY_MM');
    execute format(
      'create table if not exists silver.%I partition of silver.posts
         for values from (%L) to (%L);',
      pname,
      n,
      (n + interval '1 month')::date
    );
  end loop;
end $$;

create index if not exists silver_posts_source_dt_idx
  on silver.posts (source, datetime_utc desc);

create index if not exists silver_posts_run_id_idx
  on silver.posts (run_id);

create index if not exists silver_posts_lang_idx
  on silver.posts (lang)
  where lang is not null;

comment on table silver.posts is
  'Silver: posts limpios. Particionada mensualmente por cleaned_at.';
