"""
Smoke tests del flow pipeline_e2e (A5).

Cubre los caminos criticos sin tocar Supabase ni red:
  - Camino feliz (gate=PASS): bronze -> silver -> gate -> gold -> refresh,
    runs.finish(success).
  - Gate=FAIL: gold no se invoca, runs.finish(quality_failed).
  - Bronze=0 (CSV vacio o duplicado por sha): corto-circuito a success.
  - Silver=0 (todo duplicado en silver): corto-circuito a success.
  - Excepcion en silver: runs.finish(failed) y se re-lanza.
"""

from __future__ import annotations

import pytest

from data_pipeline.flows.pipeline_e2e import pipeline_e2e


def test_happy_path_pass(stub_supabase):
    summary = pipeline_e2e("/fake/path.csv", "twitter")

    assert summary["status"] == "success"
    assert summary["rows_bronze"] == 10
    assert summary["rows_silver"] == 10
    assert summary["rows_gold"] == 10
    assert summary["quality_overall"] == "PASS"

    stub_supabase.runs_start.assert_called_once_with("e2e")
    stub_supabase.bronze_load.assert_called_once()
    stub_supabase.silver_promote.assert_called_once()
    stub_supabase.run_gate.assert_called_once()
    stub_supabase.gold_promote.assert_called_once()
    stub_supabase.refresh_views.assert_called_once()

    # runs.finish con status=success
    args, kwargs = stub_supabase.runs_finish.call_args
    assert kwargs.get("status") == "success"
    assert kwargs.get("rows_out") == 10


def test_gate_fail_blocks_gold(stub_supabase):
    stub_supabase.run_gate.return_value = {
        "overall": "FAIL",
        "total_records": 10,
        "checks": [{"check": "completeness", "status": "FAIL"}],
    }

    summary = pipeline_e2e("/fake/path.csv", "twitter")

    assert summary["status"] == "quality_failed"
    assert summary["quality_overall"] == "FAIL"
    assert summary["rows_gold"] == 0

    # Gold/refresh NO debieron correr
    stub_supabase.gold_promote.assert_not_called()
    stub_supabase.refresh_views.assert_not_called()

    args, kwargs = stub_supabase.runs_finish.call_args
    assert kwargs.get("status") == "quality_failed"


def test_gate_warn_promotes_gold(stub_supabase):
    """WARN no bloquea — debe llegar a gold."""
    stub_supabase.run_gate.return_value = {
        "overall": "WARN",
        "total_records": 10,
        "checks": [{"check": "freshness", "status": "WARN"}],
    }

    summary = pipeline_e2e("/fake/path.csv", "twitter")

    assert summary["status"] == "success"
    assert summary["quality_overall"] == "WARN"
    stub_supabase.gold_promote.assert_called_once()


def test_empty_bronze_short_circuits(stub_supabase):
    """CSV vacio o dup-por-sha: bronze=0 -> termina success sin tocar silver."""
    stub_supabase.bronze_load.return_value = 0

    summary = pipeline_e2e("/fake/empty.csv", "twitter")

    assert summary["status"] == "success"
    assert summary["rows_bronze"] == 0
    stub_supabase.silver_promote.assert_not_called()
    stub_supabase.run_gate.assert_not_called()
    stub_supabase.gold_promote.assert_not_called()


def test_empty_silver_short_circuits(stub_supabase):
    """Bronze tuvo rows pero silver dedup deja 0: no corre gate ni gold."""
    stub_supabase.silver_promote.return_value = 0

    summary = pipeline_e2e("/fake/path.csv", "twitter")

    assert summary["status"] == "success"
    assert summary["rows_silver"] == 0
    stub_supabase.run_gate.assert_not_called()
    stub_supabase.gold_promote.assert_not_called()


def test_silver_exception_marks_failed_and_raises(stub_supabase):
    stub_supabase.silver_promote.side_effect = RuntimeError("supabase down")

    with pytest.raises(RuntimeError, match="supabase down"):
        pipeline_e2e("/fake/path.csv", "twitter")

    args, kwargs = stub_supabase.runs_finish.call_args
    assert kwargs.get("status") == "failed"
    assert "supabase down" in (kwargs.get("error") or "")
