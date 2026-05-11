-- Migration: public views (consumidas por el front via PostgREST)
-- El front solo lee de public. Aqui declaramos las vistas materializadas y
-- vistas regulares que conforman el contrato hacia React.

-- ── Vista 1: sentiment diario por fuente ────────────────────────────────
create materialized view if not exists public.v_sentiment_daily as
select
  date_trunc('day', datetime_utc)::date                as day,
  source,
  count(*)                                             as posts,
  count(*) filter (where sentiment_label = 'positive') as positive_count,
  count(*) filter (where sentiment_label = 'negative') as negative_count,
  count(*) filter (where sentiment_label = 'neutral')  as neutral_count,
  avg(sentiment_score) filter (where sentiment_score is not null) as avg_sentiment
from gold.features
where datetime_utc is not null
group by 1, 2
with no data;

create unique index if not exists v_sentiment_daily_pk
  on public.v_sentiment_daily (day, source);

comment on materialized view public.v_sentiment_daily is
  'Sentiment diario por fuente. Refrescar al cierre del flow refresh_views (concurrently).';


-- ── Vista 2: salud del pipeline (ultimas 50 corridas) ───────────────────
create or replace view public.v_pipeline_health as
select
  run_id,
  flow_name,
  status,
  started_at,
  finished_at,
  extract(epoch from (finished_at - started_at))::int as duration_seconds,
  rows_in,
  rows_out,
  quality_summary
from ops.pipeline_runs
order by started_at desc
limit 50;

comment on view public.v_pipeline_health is
  'Ultimas 50 corridas del pipeline. Lo consume la pagina Pipeline ops del front.';


-- ── Vista 3: volumen por fuente (ultimos 7 dias) ────────────────────────
create or replace view public.v_sources_volume_7d as
select
  source,
  date_trunc('day', datetime_utc)::date as day,
  count(*) as posts
from gold.features
where datetime_utc >= now() - interval '7 days'
  and datetime_utc is not null
group by source, 2
order by day desc, source;

comment on view public.v_sources_volume_7d is
  'Volumen por fuente y dia (7d). Lo consume la pagina Overview del front.';


-- ── Vista 4: ultima corrida exitosa por flow ────────────────────────────
create or replace view public.v_last_success_by_flow as
select distinct on (flow_name)
  flow_name,
  run_id,
  started_at,
  finished_at,
  rows_out
from ops.pipeline_runs
where status = 'success'
order by flow_name, started_at desc;

comment on view public.v_last_success_by_flow is
  'Una fila por flow con el run exitoso mas reciente. Util para badges de salud.';
