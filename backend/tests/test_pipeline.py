"""End-to-end checks on the small size (same code path as full). Run from backend/: python -m pytest -q"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import detect, run  # noqa: E402


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Run a in this process and b in a fresh Python process (different hash seed, nothing shared in memory)."""
    base = tmp_path_factory.mktemp("out")
    a = run.run("small", base / "a", quiet=True)
    subprocess.run([sys.executable, "-m", "app.pipeline.run", "--size", "small", "--out", str(base / "b")],
                   cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True)
    m2 = json.loads((base / "b" / "reports" / "manifest.json").read_text(encoding="utf-8"))
    return base, a, (None, None, m2)


def test_same_seed_same_output_across_processes(runs):
    _, (_, _, m1), (_, _, m2) = runs
    assert m1["files"] == m2["files"]
    assert m1["combined_sha256"] == m2["combined_sha256"]


def test_integrity_checks_pass(runs):
    _, (summary, _, _), _ = runs
    failed = [c for c in summary["checks"] if c["category"] == "integrity" and c["status"] != "PASS"]
    assert failed == []
    assert summary["sqlite_foreign_key_violations"] == 0
    assert summary["stock_equation_totals"]["balances"]


def test_business_rules_flag_exactly_the_planted_errors(runs):
    base, (summary, _, _), _ = runs
    gt = pd.read_csv(base / "a" / "ground_truth" / "csv" / "anomalies.csv")
    planted = gt.anomaly_type.value_counts()
    flagged = {c["check"]: c["failing_rows"] for c in summary["checks"] if c["category"] == "business_rule"}
    assert flagged["movement store = its shift's store"] == planted["WRONG_STORE"]
    assert flagged["adjustment has a reason"] == planted["MISSING_REASON"]
    assert flagged["count_ts not before system_qty_as_of_ts"] == planted["COUNT_BEFORE_MOVEMENTS"]
    assert flagged["transfer written off at most once"] == planted["TRANSFER_DOUBLE_LOSS"]


def test_detector_finds_planted_cases_and_spares_innocent_ones(runs):
    _, (_, ev, _), _ = runs
    for row in ev["per_type"]:
        assert row["recall"] == 1.0 and row["precision"] == 1.0, row
    ic = ev["innocent_checks"]
    assert ic["decoy_damage_event_rows"] > 0 and ic["decoy_rows_in_theft_alerts"] == 0
    assert ic["damaged_return_writeoffs_in_theft_alerts"] == 0
    assert ic["honest_transit_losses_flagged"] == 0


def test_no_answer_key_in_input_data(runs, tmp_path):
    base, _, _ = runs
    data = base / "a" / "data" / "csv"
    for f in data.glob("*.csv"):
        cols = pd.read_csv(f, nrows=0).columns.str.lower()
        assert not any(w in c for c in cols for w in ("anomal", "label", "tag", "is_fraud", "ground")), f.name
    # detector gives identical alerts with the answer key deleted
    copy = tmp_path / "a"
    shutil.copytree(base / "a" / "data", copy / "data")
    before = pd.read_csv(base / "a" / "alerts" / "csv" / "shrinkage_alert.csv")
    after = detect.detect(copy / "data")["shrinkage_alert"]
    assert list(after.alert_id) == list(before.alert_id)
    assert list(after.reason_text) == list(before.reason_text)


def test_every_alert_has_evidence_and_reasons(runs):
    base, _, _ = runs
    a = pd.read_csv(base / "a" / "alerts" / "csv" / "shrinkage_alert.csv")
    ev = pd.read_csv(base / "a" / "alerts" / "csv" / "alert_evidence.csv")
    assert set(a.alert_id) == set(ev.alert_id)
    assert a.reason_text.str.len().min() > 60
