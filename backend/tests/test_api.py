"""API tests against a fresh small run written to a temp folder. Run from backend/: python -m pytest -q"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline import run  # noqa: E402
from app.services import results  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory, monkeypatch_module):
    root = tmp_path_factory.mktemp("api")
    run.run("small", root / "small", quiet=True)
    monkeypatch_module.setattr(results, "OUTPUT_ROOT", root)
    monkeypatch_module.setattr(results, "run_dir", lambda size: root / size)
    monkeypatch_module.setattr(settings, "DATABASE_URL", "")   # always local SQLite, never a real database
    return TestClient(app)


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_health_and_runs(client):
    assert client.get("/api/health").json()["status"] == "ok"
    runs = {r["size"]: r for r in client.get("/api/runs").json()}
    assert runs["small"]["available"] and not runs["full"]["available"]


def test_overview(client):
    o = client.get("/api/small/overview").json()
    assert o["integrity_passed"] and o["stock_equation"]["balances"]
    assert o["evaluation"]["overall"]["recall"] == 1.0


def test_alert_list_filter_and_detail(client):
    page = client.get("/api/small/alerts", params={"classification": "SUSPECTED_THEFT"}).json()
    assert page["total"] > 0 and all(a["classification"] == "SUSPECTED_THEFT" for a in page["items"])
    d = client.get(f"/api/small/alerts/{page['items'][0]['alert_id']}").json()
    assert d["evidence"]["total"] > 0 and d["investigation"]["status"] == "OPEN"
    assert d["ground_truth_match"], "a theft alert in the small run should match a planted case"


def test_ground_truth_outcomes(client):
    rows = client.get("/api/small/ground-truth").json()
    assert {r["outcome"] for r in rows} <= {"CAUGHT", "CORRECTLY_IGNORED"}


def test_errors(client):
    assert client.get("/api/full/overview").status_code == 404          # no full run in the temp folder
    assert client.get("/api/small/alerts/SHR-0000-000000").status_code == 404
    assert client.get("/api/huge/overview").status_code == 422          # unknown size
