"""
conftest.py — Aisla los flows de Supabase para los smoke tests.

Mockea los puntos donde el flow toca red/DB:
  - data_pipeline.loaders.runs.start / finish
  - data_pipeline.loaders.bronze.load_csv
  - data_pipeline.loaders.silver.promote_run     (a traves del task wrapper)
  - data_pipeline.loaders.gold.promote_run       (a traves del task wrapper)
  - data_pipeline.loaders.gold.refresh_views
  - data_pipeline.quality.gate.run_gate          (a traves del task wrapper)

El parche se aplica en los modulos donde se IMPORTA (no donde se define),
porque los flows hicieron `from data_pipeline.loaders import bronze, runs`
y luego llaman bronze.load_csv / runs.start. Si parcheamos el modulo
origen, los nombres importados ya estan resueltos.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def stub_supabase(monkeypatch):
    """
    Fixture autouse: cada test arranca con todos los puntos de red mockeados.
    Los tests pueden re-parchear con valores distintos via monkeypatch.

    Yields:
        SimpleNamespace con todos los mocks para que el test pueda
        inspeccionar .call_args / .call_count.
    """
    from types import SimpleNamespace

    # runs.* — usado por pipeline_e2e directamente
    mock_start = MagicMock(return_value="00000000-0000-0000-0000-000000000001")
    mock_finish = MagicMock()
    monkeypatch.setattr("data_pipeline.loaders.runs.start", mock_start)
    monkeypatch.setattr("data_pipeline.loaders.runs.finish", mock_finish)

    # bronze.load_csv — usado por pipeline_e2e a traves del task wrapper.
    # Por defecto: 10 filas bronze nuevas.
    mock_bronze_load = MagicMock(return_value=10)
    monkeypatch.setattr(
        "data_pipeline.loaders.bronze.load_csv", mock_bronze_load
    )

    # silver.promote_run — usado por bronze_to_silver flow
    mock_silver_promote = MagicMock(return_value=10)
    monkeypatch.setattr(
        "data_pipeline.loaders.silver.promote_run", mock_silver_promote
    )

    # gate.run_gate — usado por quality_gate flow.
    # Por defecto: PASS.
    mock_run_gate = MagicMock(
        return_value={
            "overall": "PASS",
            "total_records": 10,
            "checks": [],
        }
    )
    monkeypatch.setattr("data_pipeline.quality.gate.run_gate", mock_run_gate)

    # gold.promote_run / refresh_views — usado por silver_to_gold / refresh_views
    mock_gold_promote = MagicMock(return_value=10)
    mock_refresh = MagicMock()
    monkeypatch.setattr(
        "data_pipeline.loaders.gold.promote_run", mock_gold_promote
    )
    monkeypatch.setattr(
        "data_pipeline.loaders.gold.refresh_views", mock_refresh
    )

    return SimpleNamespace(
        runs_start=mock_start,
        runs_finish=mock_finish,
        bronze_load=mock_bronze_load,
        silver_promote=mock_silver_promote,
        run_gate=mock_run_gate,
        gold_promote=mock_gold_promote,
        refresh_views=mock_refresh,
    )
