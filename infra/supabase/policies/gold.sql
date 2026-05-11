-- Mirror legible — RLS de gold.*
-- Canonico: ../migrations/20260509120700__rls_policies.sql

alter table gold.features enable row level security;

create policy "service_role full access"
  on gold.features
  as permissive
  for all
  to service_role
  using (true)
  with check (true);
