-- Migration: storage buckets
-- Crea los buckets que usa el pipeline. Idempotente (on conflict do nothing).
-- bronze-raw: CSV/JSON crudos del scraper (path: <source>/<YYYY-MM-DD>/<file>).
-- exports:    salidas auditables (reportes calidad, dumps semanales).
--
-- Ambos privados: solo service_role accede. El front nunca toca Storage.

insert into storage.buckets (id, name, public)
values ('bronze-raw', 'bronze-raw', false)
on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
values ('exports', 'exports', false)
on conflict (id) do nothing;

-- Nota: las policies sobre storage.objects se declaran en la migracion
-- 20260509120700__rls_policies.sql junto al resto del modelo de seguridad.
