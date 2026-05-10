-- Mirror legible — RLS de ops.*
-- Canonico: ../migrations/20260509120700__rls_policies.sql

alter table ops.pipeline_runs   enable row level security;
alter table ops.quality_reports enable row level security;
alter table ops.alerts          enable row level security;

create policy "service_role full access"
  on ops.pipeline_runs
  as permissive for all to service_role
  using (true) with check (true);

create policy "service_role full access"
  on ops.quality_reports
  as permissive for all to service_role
  using (true) with check (true);

create policy "service_role full access"
  on ops.alerts
  as permissive for all to service_role
  using (true) with check (true);
