"""Read pipeline outputs and run the pipeline in the background.

Storage: Postgres/Supabase when DATABASE_URL is set (app/db.py), else each run's local SQLite file + JSON reports.
All SQL here is written to run unchanged on both."""
import json
import shutil
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd

from app import db
from app.pipeline import config
from app.pipeline import run as pipeline
from app.pipeline.run import OUTPUT_ROOT

SIZES = list(config.SIZES)


NotAvailable = db.NotAvailable


def run_dir(size: str) -> Path:
    return OUTPUT_ROOT / size


def available(size: str) -> bool:
    if db.enabled():
        return db.available(size)
    return (run_dir(size) / "reports" / "manifest.json").exists()


def require(size: str) -> Path:
    if not available(size):
        raise NotAvailable(f"No '{size}' run yet. Start one with POST /api/runs.")
    return run_dir(size)


def report(size: str, name: str, optional=False):
    if db.enabled():
        body = db.report(size, name)
        if body is None and not optional:
            raise NotAvailable(f"Report '{name}' missing for '{size}'.")
        return body
    p = require(size) / "reports" / f"{name}.json"
    if optional and not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def query(size: str, sql: str, params=()):
    if db.enabled():
        return db.query(size, sql, params)
    con = sqlite3.connect(require(size) / "data" / "shrinkage.sqlite")
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def one(size, sql, params=()):
    rows = query(size, sql, params)
    return rows[0] if rows else None


def where_in(size, sql_prefix, col, ids, limit=500):
    ids = list(ids)[:limit]
    if not ids:
        return []
    return query(size, f"{sql_prefix} WHERE {col} IN ({','.join('?' * len(ids))})", ids)


# ---------- read side ----------
def overview(size):
    m, v, e = report(size, "manifest"), report(size, "validation_summary"), report(size, "evaluation")
    checks = v["checks"]
    return {
        "size": size, "seed": m["seed"], "combined_sha256": m["combined_sha256"],
        "row_counts": v["row_counts"], "integrity_passed": v["integrity_passed"],
        "checks": {"total": len(checks), "passed": sum(c["status"] == "PASS" for c in checks),
                   "business_rule_flags": [c for c in checks if c["category"] == "business_rule"]},
        "stock_equation": v["stock_equation_totals"],
        "sqlite_foreign_key_violations": v.get("sqlite_foreign_key_violations"),
        "evaluation": e,
        "reproducibility": report(size, "reproducibility", optional=True),
        "alerts_by_type": query(size, """SELECT alert_type, classification, COUNT(*) AS alerts,
                                         ROUND(CAST(SUM(loss_value_inr) AS NUMERIC), 2) AS loss_value_inr
                                         FROM shrinkage_alert GROUP BY 1, 2 ORDER BY alerts DESC, alert_type"""),
        "top_stores": query(size, """SELECT a.store_id, s.store_name, s.city, COUNT(*) AS alerts,
                                     SUM(CASE WHEN a.classification = 'SUSPECTED_THEFT' THEN 1 ELSE 0 END) AS theft_alerts,
                                     ROUND(CAST(SUM(a.loss_value_inr) AS NUMERIC), 2) AS loss_value_inr
                                     FROM shrinkage_alert a JOIN store s USING (store_id)
                                     GROUP BY a.store_id, s.store_name, s.city ORDER BY loss_value_inr DESC, a.store_id LIMIT 8"""),
    }


ALERT_SELECT = """SELECT a.*, s.store_name, s.city, e.first_name || ' ' || e.last_name AS employee_name, r.role_name
                  FROM shrinkage_alert a JOIN store s USING (store_id)
                  LEFT JOIN employee e ON e.employee_id = a.employee_id LEFT JOIN role r ON r.role_id = a.role_id"""


def alerts(size, alert_type=None, classification=None, severity=None, store_id=None, q=None, limit=50, offset=0):
    cond, params = [], []
    for col, val in (("a.alert_type", alert_type), ("a.classification", classification),
                     ("a.severity", severity), ("a.store_id", store_id)):
        if val:
            cond.append(f"{col} = ?")
            params.append(val)
    if q:
        cond.append("(a.reason_text LIKE ? OR a.alert_id LIKE ? OR a.employee_id LIKE ? OR a.sku_id LIKE ?)")
        params += [f"%{q}%"] * 4
    where = f" WHERE {' AND '.join(cond)}" if cond else ""
    total = query(size, f"SELECT COUNT(*) AS n FROM shrinkage_alert a{where}", params)[0]["n"]
    items = query(size, f"{ALERT_SELECT}{where} ORDER BY a.risk_score DESC, a.alert_id LIMIT ? OFFSET ?",
                  params + [limit, offset])
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def ground_truth_frame(size):
    if db.enabled():
        return db.ground_truth(size)
    return pd.read_csv(require(size) / "ground_truth" / "csv" / "anomalies.csv").fillna("")


def _alert_keys(size):
    """alert_id -> (alert_type, classification, {ids it points at})"""
    keys = {a["alert_id"]: (a["alert_type"], a["classification"], {a["employee_id"]} - {None})
            for a in query(size, "SELECT alert_id, alert_type, classification, employee_id FROM shrinkage_alert")}
    for r in query(size, "SELECT alert_id, evidence_id FROM alert_evidence"):
        keys[r["alert_id"]][2].add(r["evidence_id"])
    return keys


def ground_truth(size):
    """Answer key + whether the detector caught each planted case (or wrongly called a decoy theft)."""
    keys = _alert_keys(size)
    rows = []
    for g in ground_truth_frame(size).to_dict("records"):
        if g["label"] == "DECOY":
            related = set(g["related_ids"].split(";"))
            hits = [aid for aid, (_, cls, ids) in keys.items() if cls == "SUSPECTED_THEFT" and ids & related]
            g["outcome"] = "WRONGLY_FLAGGED" if hits else "CORRECTLY_IGNORED"
        else:
            hits = [aid for aid, (kind, _, ids) in keys.items() if kind == g["anomaly_type"] and g["entity_id"] in ids]
            g["outcome"] = "CAUGHT" if hits else "MISSED"
        g["alert_ids"] = hits
        rows.append(g)
    return rows


def alert_detail(size, alert_id):
    a = one(size, f"{ALERT_SELECT} WHERE a.alert_id = ?", (alert_id,))
    if not a:
        return None
    ev = query(size, "SELECT evidence_type, evidence_id FROM alert_evidence WHERE alert_id = ?", (alert_id,))
    ids = {t: [r["evidence_id"] for r in ev if r["evidence_type"] == t] for t in ("MOVEMENT", "CYCLE_COUNT", "TRANSFER")}
    a["investigation"] = one(size, """SELECT i.*, e.first_name || ' ' || e.last_name AS assigned_name FROM investigation i
                                      LEFT JOIN employee e ON e.employee_id = i.assigned_employee_id WHERE i.alert_id = ?""",
                             (alert_id,))
    a["evidence"] = {
        "movements": sorted(where_in(size, """SELECT m.movement_id, m.movement_ts, m.store_id, m.sku_id, k.sku_name,
                                    m.movement_type, m.quantity, m.reason_code, m.note, m.employee_id, m.shift_id,
                                    m.transfer_id FROM inventory_movement m JOIN sku k USING (sku_id)""",
                                    "m.movement_id", ids["MOVEMENT"]), key=lambda r: r["movement_ts"]),
        "cycle_counts": where_in(size, """SELECT c.*, k.sku_name FROM cycle_count c JOIN sku k USING (sku_id)""",
                                 "c.count_id", ids["CYCLE_COUNT"]),
        "transfers": where_in(size, "SELECT * FROM transfer", "transfer_id", ids["TRANSFER"]),
        "total": len(ev),
    }
    gt = [g for g in ground_truth(size) if alert_id in g["alert_ids"]]
    a["ground_truth_match"] = [{k: g[k] for k in ("gt_id", "anomaly_type", "label", "description")} for g in gt]
    return a


def validation(size):
    v = report(size, "validation_summary")
    return {"integrity_passed": v["integrity_passed"], "checks": v["checks"],
            "sqlite_foreign_key_violations": v.get("sqlite_foreign_key_violations")}


# ---------- pipeline runs (one at a time, built in a scratch folder then swapped in) ----------
_lock = threading.Lock()
_status = {s: {"state": "idle"} for s in SIZES}


def status(size):
    s = dict(_status[size])
    s["available"] = available(size)
    if s["available"]:
        m = report(size, "manifest")
        s.update(seed=m["seed"], combined_sha256=m["combined_sha256"],
                 movements=m["files"].get("data/csv/inventory_movement.csv", {}).get("rows"))
    return s


def start_run(size, repro=False):
    if not _lock.acquire(blocking=False):
        raise RuntimeError("A pipeline run is already in progress.")
    _status[size] = {"state": "running", "repro": repro, "started_at": datetime.now().isoformat(timespec="seconds")}

    def work():
        tmp = OUTPUT_ROOT / f".{size}_building"
        try:
            (pipeline.repro if repro else pipeline.run)(size, tmp, quiet=True)
            shutil.rmtree(run_dir(size), ignore_errors=True)
            tmp.rename(run_dir(size))
            if db.enabled():   # readers keep seeing the previous run until the new schema is swapped in
                _status[size] = {**_status[size], "state": "running", "step": "loading into database"}
                db.load(size, run_dir(size), say=lambda *_: None)
            _status[size] = {**_status[size], "state": "done", "step": None, "finished_at": datetime.now().isoformat(timespec="seconds")}
        except Exception as exc:  # report failures through /api/runs instead of killing the thread silently
            shutil.rmtree(tmp, ignore_errors=True)
            _status[size] = {**_status[size], "state": "failed", "error": str(exc)}
        finally:
            _lock.release()

    threading.Thread(target=work, daemon=True).start()
    return status(size)
