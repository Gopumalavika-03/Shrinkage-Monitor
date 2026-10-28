"""Postgres parity test: load a small run into Postgres, check the API answers exactly as with SQLite.

Skipped unless TEST_DATABASE_URL points at a throwaway database (it creates schema test_small), e.g.
    docker run -d -e POSTGRES_PASSWORD=localtest -p 55432:5432 postgres:16-alpine
    TEST_DATABASE_URL=postgresql://postgres:localtest@127.0.0.1:55432/postgres python -m pytest -q tests/test_postgres.py
"""
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db, settings  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline import run  # noqa: E402
from app.services import results  # noqa: E402

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set TEST_DATABASE_URL to run Postgres tests")


def test_postgres_matches_sqlite(tmp_path, monkeypatch):
    run.run("small", tmp_path / "small", quiet=True)
    monkeypatch.setattr(results, "run_dir", lambda size: tmp_path / size)
    monkeypatch.setattr(settings, "DB_SCHEMA_PREFIX", "test")
    monkeypatch.setattr(settings, "DATABASE_URL", URL)
    db.load("small", tmp_path / "small", say=lambda *_: None)

    c = TestClient(app)
    paths = ["/api/small/overview", "/api/small/alerts?limit=500", "/api/small/validation", "/api/small/ground-truth"]
    first = c.get("/api/small/alerts?limit=1").json()["items"][0]["alert_id"]
    paths.append(f"/api/small/alerts/{first}")
    from_pg = [c.get(p).json() for p in paths]
    monkeypatch.setattr(settings, "DATABASE_URL", "")
    from_sqlite = [c.get(p).json() for p in paths]
    for p, a, b in zip(paths, from_pg, from_sqlite):
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), p

    monkeypatch.setattr(settings, "DATABASE_URL", URL)
    assert c.get("/api/full/overview").status_code == 404   # schema test_full was never loaded
