-- Mirror legible — RLS de raw.*
-- Canonico: ../migrations/20260509120700__rls_policies.sql

alter table raw.posts enable row level security;

create policy "service_role full access"
  on raw.posts
  as permissive
  for all
  to service_role
  using (true)
  with check (true);
