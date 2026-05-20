-- seed.sql — Datos demo para desarrollo local.
-- Se aplica con `supabase db reset` despues de las migraciones.
-- IMPORTANTE: no usar en prod.

-- Run de ejemplo
insert into ops.pipeline_runs (run_id, flow_name, status, started_at, finished_at, rows_in, rows_out, quality_summary)
values
  ('00000000-0000-0000-0000-000000000001', 'ingest_inbox',     'success', now() - interval '2 hours', now() - interval '2 hours' + interval '15 seconds', 320, 320, '{}'::jsonb),
  ('00000000-0000-0000-0000-000000000002', 'bronze_to_silver', 'success', now() - interval '2 hours' + interval '20 seconds', now() - interval '2 hours' + interval '40 seconds', 320, 318, '{}'::jsonb),
  ('00000000-0000-0000-0000-000000000003', 'quality_gate',     'success', now() - interval '2 hours' + interval '45 seconds', now() - interval '2 hours' + interval '50 seconds', 318, 318, '{"overall":"PASS"}'::jsonb),
  ('00000000-0000-0000-0000-000000000004', 'silver_to_gold',   'success', now() - interval '2 hours' + interval '55 seconds', now() - interval '2 hours' + interval '70 seconds', 318, 318, '{}'::jsonb),
  ('00000000-0000-0000-0000-000000000005', 'refresh_views',    'success', now() - interval '2 hours' + interval '75 seconds', now() - interval '2 hours' + interval '78 seconds', null, null, '{}'::jsonb)
on conflict (run_id) do nothing;

-- 3 posts gold de demo (sin sentiment, lo llena ML mas tarde)
insert into gold.features (id, source, datetime_utc, word_count, char_count, has_hashtags, has_emojis, hour_of_day, day_of_week, engagement_score, run_id)
values
  ('seed_tw_1', 'twitter',  now() - interval '1 day',  12, 84, true,  false, 9,  3, 0.42, '00000000-0000-0000-0000-000000000004'),
  ('seed_yt_1', 'youtube',  now() - interval '1 day',  28, 190, false, true,  14, 3, 0.61, '00000000-0000-0000-0000-000000000004'),
  ('seed_tk_1', 'tiktok',   now() - interval '12 hours', 8,  55, true,  true,  21, 3, 0.78, '00000000-0000-0000-0000-000000000004')
on conflict (id) do nothing;

-- Refrescar la matview con los datos seed
refresh materialized view public.v_sentiment_daily;
