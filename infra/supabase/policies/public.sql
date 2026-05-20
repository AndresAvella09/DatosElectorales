-- Mirror legible — Grants sobre public.v_*
-- Canonico: ../migrations/20260509120700__rls_policies.sql
--
-- Las vistas no almacenan filas: el control se hace via grants y deny por
-- defecto en privilegios futuros.

grant usage on schema public to anon, authenticated;

grant select on public.v_sentiment_daily      to anon, authenticated;
grant select on public.v_pipeline_health      to anon, authenticated;
grant select on public.v_sources_volume_7d    to anon, authenticated;
grant select on public.v_last_success_by_flow to anon, authenticated;

alter default privileges in schema public
  revoke all on tables from anon, authenticated;
