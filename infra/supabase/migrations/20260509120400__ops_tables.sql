-- Migration: ops tables
-- Trazabilidad y observabilidad del pipeline.

create table if not exists ops.pipeline_runs (
  run_id          uuid primary key,
  flow_name       text not null,
  status          text not null check (status in ('running','success','failed','quality_failed')),
  started_at      timestamptz not null,
  finished_at     timestamptz,
  rows_in         int,
  rows_out        int,
  quality_summary jsonb,
  error           text
);

create index if not exists pipeline_runs_started_idx
  on ops.pipeline_runs (started_at desc);

create index if not exists pipeline_runs_status_idx
  on ops.pipeline_runs (status, started_at desc);

create index if not exists pipeline_runs_flow_idx
  on ops.pipeline_runs (flow_name, started_at desc);

comment on table ops.pipeline_runs is
  'Una fila por corrida de flow. Insertar al inicio (status=running) y actualizar al final.';


create table if not exists ops.quality_reports (
  run_id     uuid not null references ops.pipeline_runs(run_id) on delete cascade,
  layer      text not null check (layer in ('silver','gold')),
  overall    text not null check (overall in ('PASS','WARN','FAIL')),
  checks     jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  primary key (run_id, layer)
);

create index if not exists quality_reports_overall_idx
  on ops.quality_reports (overall, created_at desc);

comment on table ops.quality_reports is
  'Quality Gate: 1 fila por (run_id, layer). overall=FAIL bloquea promocion a gold.';


create table if not exists ops.alerts (
  id          uuid primary key default gen_random_uuid(),
  run_id      uuid references ops.pipeline_runs(run_id) on delete set null,
  severity    text not null check (severity in ('INFO','WARNING','CRITICAL')),
  channel     text not null,                 -- 'slack' | 'discord' | 'email'
  payload     jsonb not null default '{}'::jsonb,
  delivered   boolean not null default false,
  delivered_at timestamptz,
  created_at  timestamptz not null default now()
);

create index if not exists alerts_severity_idx
  on ops.alerts (severity, created_at desc);

create index if not exists alerts_undelivered_idx
  on ops.alerts (created_at)
  where delivered = false;

comment on table ops.alerts is
  'Cola de alertas operativas. delivered=false son pendientes de envio (worker A10).';
