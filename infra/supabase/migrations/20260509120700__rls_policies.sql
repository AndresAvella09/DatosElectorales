-- Migration: RLS policies
-- Politica por defecto: deniega todo. Solo service_role escribe en raw/silver/
-- gold/ops. anon y authenticated solo leen public.v_*.
--
-- Mirror legible (no ejecutable por separado): infra/supabase/policies/*.sql

-- ── 1. Habilitar RLS en todas las tablas internas ──────────────────────
alter table raw.posts            enable row level security;
alter table silver.posts         enable row level security;
alter table gold.features        enable row level security;
alter table ops.pipeline_runs    enable row level security;
alter table ops.quality_reports  enable row level security;
alter table ops.alerts           enable row level security;

-- ── 2. service_role tiene acceso completo (RLS no aplica al rol pero las
--      policies explicitas dejan claro el contrato) ───────────────────────

-- raw
drop policy if exists "service_role full access" on raw.posts;
create policy "service_role full access"
  on raw.posts
  as permissive
  for all
  to service_role
  using (true)
  with check (true);

-- silver
drop policy if exists "service_role full access" on silver.posts;
create policy "service_role full access"
  on silver.posts
  as permissive
  for all
  to service_role
  using (true)
  with check (true);

-- gold
drop policy if exists "service_role full access" on gold.features;
create policy "service_role full access"
  on gold.features
  as permissive
  for all
  to service_role
  using (true)
  with check (true);

-- ops.pipeline_runs
drop policy if exists "service_role full access" on ops.pipeline_runs;
create policy "service_role full access"
  on ops.pipeline_runs
  as permissive
  for all
  to service_role
  using (true)
  with check (true);

-- ops.quality_reports
drop policy if exists "service_role full access" on ops.quality_reports;
create policy "service_role full access"
  on ops.quality_reports
  as permissive
  for all
  to service_role
  using (true)
  with check (true);

-- ops.alerts
drop policy if exists "service_role full access" on ops.alerts;
create policy "service_role full access"
  on ops.alerts
  as permissive
  for all
  to service_role
  using (true)
  with check (true);

-- ── 3. anon / authenticated: solo SELECT en public.v_* ─────────────────
-- Los views/matviews se crean en schema public; otorgamos SELECT explicito.
-- (No tienen RLS porque las vistas no almacenan filas; el control esta en el
-- schema public + grants.)

grant usage  on schema public to anon, authenticated;
grant select on public.v_sentiment_daily   to anon, authenticated;
grant select on public.v_pipeline_health   to anon, authenticated;
grant select on public.v_sources_volume_7d to anon, authenticated;
grant select on public.v_last_success_by_flow to anon, authenticated;

-- Negar SELECT en cualquier tabla future de public por defecto.
alter default privileges in schema public revoke all on tables from anon, authenticated;

-- ── 4. Storage: bronze-raw y exports solo service_role ─────────────────
-- storage.objects ya tiene RLS habilitado por Supabase.

drop policy if exists "service_role manages bronze-raw" on storage.objects;
create policy "service_role manages bronze-raw"
  on storage.objects
  as permissive
  for all
  to service_role
  using (bucket_id = 'bronze-raw')
  with check (bucket_id = 'bronze-raw');

drop policy if exists "service_role manages exports" on storage.objects;
create policy "service_role manages exports"
  on storage.objects
  as permissive
  for all
  to service_role
  using (bucket_id = 'exports')
  with check (bucket_id = 'exports');

-- anon/authenticated NO tienen policy sobre estos buckets => deny por defecto.
