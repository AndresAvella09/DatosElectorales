"""
Tests minimos de la API (A7) — sin depender de Supabase real.

Estrategia:
  - Cliente Supabase mockeado con un FakeBuilder que emula la API
    encadenada de supabase-py (.table().select().order().limit().execute()).
  - Cada test inyecta el fake via apps.api.deps.get_supabase override.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apps.api.deps as deps_module
from apps.api.main import app

RUN_1 = "11111111-1111-1111-1111-111111111111"
RUN_2 = "22222222-2222-2222-2222-222222222222"

_RUNS = [
    {
        "run_id": RUN_1,
        "flow_name": "bronze_to_silver",
        "status": "success",
        "started_at": "2026-05-09T10:00:00+00:00",
        "finished_at": "2026-05-09T10:02:00+00:00",
        "duration_seconds": 120,
        "rows_in": 100,
        "rows_out": 98,
        "quality_summary": {"overall": "PASS"},
        "error": None,
    },
    {
        "run_id": RUN_2,
        "flow_name": "bronze_to_silver",
        "status": "quality_failed",
        "started_at": "2026-05-09T09:00:00+00:00",
        "finished_at": "2026-05-09T09:01:00+00:00",
        "duration_seconds": 60,
        "rows_in": 50,
        "rows_out": 48,
        "quality_summary": {"overall": "FAIL"},
        "error": None,
    },
]

_QUALITY = [
    {
        "run_id": RUN_2,
        "layer": "silver",
        "overall": "FAIL",
        "checks": [{"check": "completeness", "status": "FAIL"}],
        "created_at": "2026-05-09T09:01:00+00:00",
    },
]

_VOLUME = [{"source": "twitter", "posts": 42}]
_LAST_SUCCESS = [
    {
        "flow_name": "bronze_to_silver",
        "run_id": RUN_1,
        "started_at": "2026-05-09T10:00:00+00:00",
        "finished_at": "2026-05-09T10:02:00+00:00",
        "rows_out": 98,
    }
]
_SENTIMENT = [
    {
        "source": "twitter",
        "posts": 42,
        "positive_count": 20,
        "negative_count": 10,
        "neutral_count": 12,
        "avg_sentiment": 0.4,
    }
]


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, data):
        self._data = data
        self._filters: dict = {}

    def select(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def gte(self, *args, **kwargs):
        return self

    def execute(self):
        data = self._data
        for col, val in self._filters.items():
            data = [r for r in data if r.get(col) == val]
        return FakeResult(data)


class FakeSchema:
    def __init__(self, data_map):
        self._data_map = data_map

    def table(self, name):
        return FakeQuery(self._data_map.get(name, []))


class FakeClient:
    def __init__(self, data_map, public_map):
        self._data_map = data_map
        self._public_map = public_map

    def schema(self, name):
        if name == "ops":
            return FakeSchema(self._data_map)
        return FakeSchema(self._public_map)

    def table(self, name):
        return FakeQuery(self._public_map.get(name, []))


@pytest.fixture()
def client_with_fake():
    fake = FakeClient(
        data_map={
            "pipeline_runs": _RUNS,
            "quality_reports": _QUALITY,
        },
        public_map={
            "v_pipeline_health": _RUNS,
            "v_sources_volume_7d": _VOLUME,
            "v_last_success_by_flow": _LAST_SUCCESS,
            "v_sentiment_daily": _SENTIMENT,
        },
    )
    app.dependency_overrides[deps_module.get_supabase] = lambda: fake
    deps_module.reset_supabase()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_root_ok(client_with_fake):
    r = client_with_fake.get("/docs")
    assert r.status_code == 200
    info = client_with_fake.get("/openapi.json").json()
    assert info["info"]["title"] == "DatosElectorales API"
    assert any(p == "/health" for p in info["paths"])


def test_health_ok(client_with_fake):
    r = client_with_fake.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "supabase_reachable" in body


def test_runs_list(client_with_fake):
    r = client_with_fake.get("/v1/runs")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["items"][0]["flow_name"] == "bronze_to_silver"


def test_runs_filter_by_status(client_with_fake):
    r = client_with_fake.get("/v1/runs?status=quality_failed")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["status"] == "quality_failed"


def test_runs_get_by_id(client_with_fake):
    r = client_with_fake.get(f"/v1/runs/{RUN_1}")
    assert r.status_code == 200
    assert r.json()["status"] == "success"


def test_runs_get_404(client_with_fake):
    r = client_with_fake.get("/v1/runs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_quality_list(client_with_fake):
    r = client_with_fake.get("/v1/quality")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["overall"] == "FAIL"


def test_quality_by_run(client_with_fake):
    r = client_with_fake.get(f"/v1/quality/{RUN_2}")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_quality_404(client_with_fake):
    r = client_with_fake.get("/v1/quality/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_metrics_summary(client_with_fake):
    r = client_with_fake.get("/v1/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["sources_volume_7d"][0]["source"] == "twitter"
    assert isinstance(body["last_success_by_flow"], list)
    assert isinstance(body["quality_failed_rate"], list)
    assert body["quality_failed_rate"][0]["window"] in ("24h", "7d")


def test_metrics_subendpoints(client_with_fake):
    for path in [
        "/v1/metrics/sources_volume_7d",
        "/v1/metrics/last_success_by_flow",
        "/v1/metrics/sentiment_daily",
        "/v1/metrics/quality_failed_rate",
    ]:
        r = client_with_fake.get(path)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
