"""Rule-based shrinkage detector + evaluation.

detect() reads only the exported input CSVs -- never ground_truth -- and returns
shrinkage_alert, alert_evidence and investigation tables. evaluate() then scores the
alerts against ground_truth (precision / recall per planted type, decoys wrongly flagged).
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .schema import TABLES

TS_COLS = {"inventory_movement": ["movement_ts"], "cycle_count": ["system_qty_as_of_ts", "count_ts"],
           "transfer": ["shipped_ts", "received_ts"]}
NEEDED = ["inventory_movement", "shift", "shift_assignment", "cycle_count", "transfer", "role", "employee_role", "employee"]
WRITE_OFF = ["DAMAGE", "EXPIRED", "MISCOUNT"]
BASE_SCORE = {"WRONG_STORE": 35, "MISSING_REASON": 30, "COUNT_BEFORE_MOVEMENTS": 30, "TRANSFER_DOUBLE_LOSS": 40,
              "REPEATED_ADJUSTMENTS": 60, "UNEXPLAINED_LOSS": 60}
INV_TYPE = {"SUSPECTED_THEFT": "LOSS_PREVENTION", "DATA_ERROR": "DATA_CORRECTION", "PROCESS_ERROR": "PROCESS_COACHING"}
ACTION = {
    "WRONG_STORE": "Re-book the movement to the shift's store with a correcting entry; check the delivery paperwork.",
    "MISSING_REASON": "Get the reason from the employee and post it as a new annotated entry; coach on mandatory reason codes.",
    "COUNT_BEFORE_MOVEMENTS": "Recount the item; freeze book stock at the moment counting starts.",
    "TRANSFER_DOUBLE_LOSS": "Reverse the sending store's duplicate write-off; confirm with the carrier which store bears the loss.",
    "REPEATED_ADJUSTMENTS": "Check CCTV and the damaged-goods bin for the listed shifts; require supervisor sign-off on this "
                            "employee's write-offs.",
    "UNEXPLAINED_LOSS": "Recount the listed SKUs, review POS voids and CCTV around the last-handled movements, interview the employee.",
}


def load(data_dir):
    d = Path(data_dir) / "csv"
    return {n: pd.read_csv(d / f"{n}.csv", parse_dates=TS_COLS.get(n, []), low_memory=False) for n in NEEDED}


def poisson_sf(k, lam):
    """P(X >= k) for X ~ Poisson(lam)."""
    return 1.0 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k))


def binom_sf(k, n, p):
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def inr(x):
    return f"INR {x:,.0f}"


def detect(data_dir):
    t = load(data_dir)
    mv, sh, sa, cc = t["inventory_movement"], t["shift"], t["shift_assignment"], t["cycle_count"]
    role_name = t["role"].set_index("role_id").role_name
    role_of = sa.set_index(["shift_id", "employee_id"]).role_id
    alerts = []

    def alert(kind, cls, store, first, last, units, value, text, evidence, sku=None, emp=None, role=None, shift=None):
        alerts.append(dict(alert_type=kind, classification=cls, store_id=store, sku_id=sku, employee_id=emp, role_id=role,
                           shift_id=shift, first_evidence_ts=first, last_evidence_ts=last, loss_units=int(units),
                           loss_value_inr=round(float(value), 2), reason_text=text, evidence=evidence))

    def role(shift, emp):
        return role_of.get((shift, emp))

    # R1 WRONG_STORE: the movement's store differs from the store of the shift it was posted in
    m = mv.merge(sh[["shift_id", "store_id"]].rename(columns={"store_id": "shift_store"}), on="shift_id")
    for r in m[m.store_id != m.shift_store].itertuples():
        q = abs(r.quantity)
        alert("WRONG_STORE", "DATA_ERROR", r.store_id, r.movement_ts, r.movement_ts, q, q * r.unit_cost_inr,
              f"{r.movement_type.title()} {r.movement_id} ({r.quantity:+d} units) is booked to {r.store_id}, but it was "
              f"posted in shift {r.shift_id} of {r.shift_store} by {r.employee_id}. Stock at both stores is off by "
              f"{q} units until it is re-booked.",
              [("MOVEMENT", r.movement_id)], r.sku_id, r.employee_id, role(r.shift_id, r.employee_id), r.shift_id)

    # R2 MISSING_REASON: an adjustment with no reason code
    for r in mv[(mv.movement_type == "ADJUSTMENT") & mv.reason_code.isna()].itertuples():
        q = abs(r.quantity)
        rl = role(r.shift_id, r.employee_id)
        alert("MISSING_REASON", "PROCESS_ERROR", r.store_id, r.movement_ts, r.movement_ts, q, q * r.unit_cost_inr,
              f"Adjustment {r.movement_id} {'removed' if r.quantity < 0 else 'added'} {q} units ({inr(q * r.unit_cost_inr)}) "
              f"of {r.sku_id} at {r.store_id} with no reason code or note. Posted by {r.employee_id} "
              f"({role_name.get(rl, 'unknown role')}) in shift {r.shift_id}.",
              [("MOVEMENT", r.movement_id)], r.sku_id, r.employee_id, rl, r.shift_id)

    # R3 COUNT_BEFORE_MOVEMENTS: count timestamped before the book snapshot it was compared with
    early = cc[cc.count_ts < cc.system_qty_as_of_ts]
    if len(early):
        j = early.merge(mv[["store_id", "sku_id", "movement_id", "movement_ts", "quantity"]], on=["store_id", "sku_id"])
        j = j[(j.movement_ts > j.count_ts) & (j.movement_ts <= j.system_qty_as_of_ts)]
        for c in early.itertuples():
            ins = j[j.count_id == c.count_id]
            hrs = (c.system_qty_as_of_ts - c.count_ts).total_seconds() / 3600
            alert("COUNT_BEFORE_MOVEMENTS", "DATA_ERROR", c.store_id, c.count_ts, c.system_qty_as_of_ts,
                  abs(c.variance_qty), abs(c.variance_value_inr),
                  f"Count {c.count_id} of {c.sku_id} at {c.store_id} is timestamped {c.count_ts}, {hrs:.1f} h before "
                  f"the book snapshot it was compared with ({c.system_qty_as_of_ts}). {len(ins)} movement(s) "
                  f"({ins.quantity.sum():+d} units) in between are in expected_qty but were not on the shelf yet, so "
                  f"its {c.variance_qty:+d} variance cannot be trusted.",
                  [("CYCLE_COUNT", c.count_id)] + [("MOVEMENT", x) for x in ins.movement_id],
                  c.sku_id, c.employee_id, role(c.shift_id, c.employee_id), c.shift_id)

    # R4 TRANSFER_DOUBLE_LOSS: one transfer written off as lost by more than one store
    tl = mv[mv.reason_code.eq("TRANSIT_LOSS")]
    tr = t["transfer"].set_index("transfer_id")
    for tid, g in tl.groupby("transfer_id"):
        if g.store_id.nunique() < 2:
            continue
        x = tr.loc[tid]
        dup = g[g.store_id == x.from_store_id].iloc[0]
        alert("TRANSFER_DOUBLE_LOSS", "DATA_ERROR", x.from_store_id, g.movement_ts.min(), g.movement_ts.max(),
              x.quantity, x.quantity * dup.unit_cost_inr,
              f"Transfer {tid} ({x.quantity} units of {x.sku_id}, {x.from_store_id} -> {x.to_store_id}) was written off "
              f"as lost by both stores ({', '.join(g.movement_id)}). {abs(g.quantity.sum())} units are booked as loss "
              f"but only {x.quantity} went missing. The sender already booked TRANSFER_OUT, so its write-off "
              f"{dup.movement_id} is the duplicate.",
              [("TRANSFER", tid)] + [("MOVEMENT", x_) for x_ in g.movement_id],
              x.sku_id, dup.employee_id, role(dup.shift_id, dup.employee_id), dup.shift_id)

    # R5 REPEATED_ADJUSTMENTS: an employee's write-offs far above their share of the store's write-offs
    wo = mv[(mv.movement_type == "ADJUSTMENT") & (mv.quantity < 0) & (mv.reason_code.isin(WRITE_OFF) | mv.reason_code.isna())]
    wo = wo.assign(day=wo.movement_ts.dt.date)
    days = wo.groupby(["store_id", "day"]).agg(n=("movement_id", "size"), people=("employee_id", "nunique"))
    mass = days[(days.n >= config.MASS_EVENT_MIN_ADJ) & (days.people >= 3)].index
    wo = wo[~pd.MultiIndex.from_frame(wo[["store_id", "day"]]).isin(mass)]   # one-off incidents are not a pattern
    wo = wo.merge(sa, on=["shift_id", "employee_id"]).merge(sh[["shift_id", "shift_type"]], on="shift_id")
    worked = sa.merge(sh[["shift_id", "store_id"]], on="shift_id").groupby(["store_id", "role_id", "employee_id"]).size()
    x = wo.groupby(["store_id", "role_id", "employee_id"]).size()
    df = pd.DataFrame({"x": x, "shifts": worked}).dropna(subset=["x"])
    grp = df.groupby(level=["store_id", "role_id"])
    df["e"] = grp.x.transform("sum") * df.shifts / grp.shifts.transform("sum")
    df["z"] = (df.x - df.e) / np.sqrt(df.e)
    # second signal: write-offs bunched on night shifts far beyond the role's normal night share
    night_rate = wo.assign(n=wo.shift_type == "NIGHT").groupby("role_id").n.mean()
    nights = wo[wo.shift_type == "NIGHT"].groupby(["store_id", "role_id", "employee_id"]).size()
    df["nights"] = nights.reindex(df.index, fill_value=0)
    df["p_night"] = [binom_sf(int(r.nights), int(r.x), night_rate[i[1]]) for i, r in df.iterrows()]
    hit = (df.z >= config.REPEATED_ADJ_Z) | ((df.z >= config.REPEATED_ADJ_Z_WEAK) & (df.p_night < config.NIGHT_MAX_P))
    for (store, rl, emp), r in df[hit & (df.x >= 1.5 * df.e) & (df.x >= 8)].iterrows():
        mine = wo[wo.employee_id == emp]
        units, value = -mine.quantity.sum(), -(mine.quantity * mine.unit_cost_inr).sum()
        reasons = ", ".join(f"{k} {v}" for k, v in mine.reason_code.fillna("NONE").value_counts().items())
        alert("REPEATED_ADJUSTMENTS", "SUSPECTED_THEFT", store, mine.movement_ts.min(), mine.movement_ts.max(), units, value,
              f"{emp} ({role_name[rl]}, {store}) posted {int(r.x)} stock write-offs in {int(r.shifts)} shifts; their share "
              f"of shifts predicts about {r.e:.0f} (z = {r.z:.1f}). {int(r.nights)} of them ({r.nights / r.x:.0%}) were on "
              f"night shifts vs {night_rate[rl]:.0%} normally for this role (p = {r.p_night:.1e}). {units} units, "
              f"{inr(value)}. Reasons used: {reasons}. One-day mass incidents excluded.",
              [("MOVEMENT", m_) for m_ in mine.movement_id], emp=emp, role=rl)

    # R6 UNEXPLAINED_LOSS: large count shortages that keep following the same last handler
    ok = cc[cc.count_ts >= cc.system_qty_as_of_ts].sort_values("system_qty_as_of_ts")   # R3 counts are unreliable
    hand = mv[mv.reason_code.ne("COUNT_VARIANCE") | mv.reason_code.isna()]
    hand = hand[["store_id", "sku_id", "movement_ts", "movement_id", "employee_id", "shift_id"]].rename(
        columns={"employee_id": "last_emp", "shift_id": "last_shift", "movement_id": "last_mov"}).sort_values("movement_ts")
    lh = pd.merge_asof(ok, hand, left_on="system_qty_as_of_ts", right_on="movement_ts", by=["store_id", "sku_id"],
                       direction="backward").dropna(subset=["last_emp"])
    lh["big"] = lh.variance_qty <= -config.BIG_SHORTAGE_UNITS
    per = lh.groupby("last_emp").agg(n=("big", "size"), k=("big", "sum"))
    for emp, r in per[per.k >= config.UNEXPLAINED_MIN_COUNTS].iterrows():
        p0 = (lh.big.sum() - r.k) / (len(lh) - r.n)    # everyone else's rate, so a suspect can't raise their own baseline
        lam = r.n * p0
        p = poisson_sf(int(r.k), lam)
        if p >= config.UNEXPLAINED_MAX_P:
            continue
        b = lh[(lh.last_emp == emp) & lh.big]
        roles = [role(s, emp) for s in b.last_shift]
        rl = max(sorted(set(roles), key=str), key=roles.count)   # sorted: deterministic tie-break
        units, value = -b.variance_qty.sum(), -b.variance_value_inr.sum()
        alert("UNEXPLAINED_LOSS", "SUSPECTED_THEFT", b.store_id.mode()[0], b.movement_ts.min(), b.system_qty_as_of_ts.max(),
              units, value,
              f"{emp} ({role_name.get(rl, 'unknown role')}) was the last person to handle the stock before {int(r.k)} of "
              f"the {int(r.n)} counts that followed their movements showed a large shortage (>= "
              f"{config.BIG_SHORTAGE_UNITS} units). At everyone else's rate of {p0:.1%} about {lam:.1f} would be expected by "
              f"chance (p = {p:.1e}). {units} units ({inr(value)}) are missing with no write-off or reason recorded.",
              [("CYCLE_COUNT", c) for c in b.count_id] + [("MOVEMENT", m_) for m_ in b.last_mov], emp=emp, role=rl)

    return finish(alerts, t)


def finish(alerts, t):
    cols = [c["name"] for c in TABLES["shrinkage_alert"]["cols"]]
    if not alerts:
        return {"shrinkage_alert": pd.DataFrame(columns=cols), "alert_evidence": pd.DataFrame(columns=["alert_id", "evidence_type", "evidence_id"]),
                "investigation": pd.DataFrame(columns=[c["name"] for c in TABLES["investigation"]["cols"]])}
    a = pd.DataFrame(alerts)
    a["detected_ts"] = a.last_evidence_ts + pd.Timedelta(hours=1)
    a["first_ev"] = [e[0][1] for e in a.evidence]
    a = a.sort_values(["detected_ts", "alert_type", "first_ev"], kind="stable").reset_index(drop=True)
    a["alert_id"] = [f"SHR-{config.YEAR}-{i:06d}" for i in range(1, len(a) + 1)]
    a["risk_score"] = np.minimum(100, a.alert_type.map(BASE_SCORE) + 8 * np.log10(1 + a.loss_value_inr)).round(1)
    a["severity"] = np.select([a.risk_score >= 70, a.risk_score >= 40], ["HIGH", "MEDIUM"], "LOW")
    ev = pd.DataFrame([(aid, k, v) for aid, e in zip(a.alert_id, a.evidence) for k, v in e],
                      columns=["alert_id", "evidence_type", "evidence_id"]).drop_duplicates()

    er, emp = t["employee_role"], t["employee"]
    manager = emp.merge(er[er.role_id == "ROLE-04"], on="employee_id").set_index("store_id").employee_id
    inv = pd.DataFrame({
        "investigation_id": [f"INV-{config.YEAR}-{i:06d}" for i in range(1, len(a) + 1)], "alert_id": a.alert_id,
        "store_id": a.store_id, "assigned_employee_id": a.store_id.map(manager),
        "investigation_type": a.classification.map(INV_TYPE), "priority": a.severity, "status": "OPEN",
        "opened_ts": a.detected_ts + pd.Timedelta(hours=2), "recommended_action": a.alert_type.map(ACTION)})
    return {"shrinkage_alert": a[cols], "alert_evidence": ev, "investigation": inv}


def evaluate(alerts, gt, data_dir):
    a, ev = alerts["shrinkage_alert"], alerts["alert_evidence"]
    ev = ev.merge(a[["alert_id", "alert_type", "classification"]], on="alert_id")
    want_ev = {"WRONG_STORE": "MOVEMENT", "MISSING_REASON": "MOVEMENT", "COUNT_BEFORE_MOVEMENTS": "CYCLE_COUNT",
               "TRANSFER_DOUBLE_LOSS": "TRANSFER"}
    rows = []
    for kind in BASE_SCORE:
        if kind in want_ev:
            pred = set(ev[(ev.alert_type == kind) & (ev.evidence_type == want_ev[kind])].evidence_id)
        else:
            pred = set(a[a.alert_type == kind].employee_id)
        truth = set(gt[(gt.label == "ANOMALY") & (gt.anomaly_type == kind)].entity_id)
        tp = len(pred & truth)
        p = tp / len(pred) if pred else (1.0 if not truth else 0.0)
        r = tp / len(truth) if truth else 1.0
        rows.append(dict(anomaly_type=kind, unit=want_ev.get(kind, "EMPLOYEE"), planted=len(truth), flagged=len(pred),
                         tp=tp, fp=len(pred - truth), fn=len(truth - pred), precision=round(p, 3), recall=round(r, 3),
                         f1=round(2 * p * r / (p + r), 3) if p + r else 0.0))
    tp, fp, fn = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn"))

    # innocent explanations: none of these may appear as evidence in a theft alert
    theft_ids = set(ev[ev.classification == "SUSPECTED_THEFT"].evidence_id)
    decoy_ids = {i for s in gt[gt.label == "DECOY"].related_ids.dropna() for i in s.split(";")}
    mv = pd.read_csv(Path(data_dir) / "csv" / "inventory_movement.csv", usecols=["movement_id", "reason_code"])
    dmg_ret = set(mv[mv.reason_code == "DAMAGED_RETURN"].movement_id)
    honest_tl = set(mv[mv.reason_code == "TRANSIT_LOSS"].movement_id) - {
        i for s in gt[gt.anomaly_type == "TRANSFER_DOUBLE_LOSS"].related_ids for i in s.split(";")}
    cc = pd.read_csv(Path(data_dir) / "csv" / "cycle_count.csv", usecols=["count_id", "variance_qty"])
    planted = {i for s in gt[gt.anomaly_type == "UNEXPLAINED_LOSS"].related_ids for i in s.split(";")}
    honest_big = set(cc[cc.variance_qty <= -config.BIG_SHORTAGE_UNITS].count_id) - planted   # e.g. shoplifting
    return {
        "per_type": rows,
        "overall": dict(tp=tp, fp=fp, fn=fn, precision=round(tp / (tp + fp), 3) if tp + fp else 1.0,
                        recall=round(tp / (tp + fn), 3) if tp + fn else 1.0),
        "innocent_checks": {
            "decoy_damage_event_rows": len(decoy_ids),
            "decoy_rows_in_theft_alerts": len(decoy_ids & theft_ids),
            "damaged_return_writeoffs": len(dmg_ret),
            "damaged_return_writeoffs_in_theft_alerts": len(dmg_ret & theft_ids),
            "honest_transit_losses": len(honest_tl),
            "honest_transit_losses_flagged": len(honest_tl & set(ev.evidence_id)),
            "honest_large_count_shortages": len(honest_big),
            "honest_large_shortages_in_theft_alerts": len(honest_big & theft_ids),
        },
        "alerts_by_classification": a.classification.value_counts().to_dict(),
        "alerts_by_severity": a.severity.value_counts().to_dict(),
    }
