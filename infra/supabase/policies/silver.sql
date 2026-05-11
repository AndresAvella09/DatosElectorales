-- Mirror legible — RLS de silver.*
-- Canonico: ../migrations/20260509120700__rls_policies.sql

alter table silver.posts enable row level security;

create policy "service_role full access"
  on silver.posts
  as permissive
  for all
  to service_role
  using (true)
  with check (true);
