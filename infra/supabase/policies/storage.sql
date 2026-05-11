-- Mirror legible — RLS de storage.objects para los buckets del pipeline
-- Canonico: ../migrations/20260509120700__rls_policies.sql

create policy "service_role manages bronze-raw"
  on storage.objects
  as permissive for all to service_role
  using (bucket_id = 'bronze-raw')
  with check (bucket_id = 'bronze-raw');

create policy "service_role manages exports"
  on storage.objects
  as permissive for all to service_role
  using (bucket_id = 'exports')
  with check (bucket_id = 'exports');
