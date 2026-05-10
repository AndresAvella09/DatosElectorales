"""
loaders — UPSERT a Supabase de Bronze, Silver y Gold.

Cada submodulo expone una funcion principal que el orchestrator (A5) o el
CLI invocan:

    from data_pipeline.loaders import bronze, silver, gold, runs

    run_id = runs.start("ingest_inbox")
    bronze.load_csv("data/inbox/twitter/2026-05-10/run.csv",
                    source="twitter", run_id=run_id)
    silver.promote_run(run_id)
    gold.promote_run(run_id)
    runs.finish(run_id, status="success")

El cliente Supabase es un singleton con la SERVICE_ROLE_KEY (lectura/
escritura sin RLS). NO usar en frontend ni en codigo expuesto al usuario.
"""

from data_pipeline.loaders import bronze, gold, runs, silver

__all__ = ["bronze", "silver", "gold", "runs"]
