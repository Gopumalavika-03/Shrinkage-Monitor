"""Synthetic retail stock data: parents -> clean baseline -> planted problems -> calculated balances -> IDs.

Time is kept internally as float hours `h` since START 06:00 (start of day 0's MORNING shift), so
day = h // 24 and shift slot = (h % 24) // 8 (0 MORNING 06-14, 1 EVENING 14-22, 2 NIGHT 22-06).
Every planted row carries an internal `tag`; ground truth is built from the tags, and tags are
dropped before export, so nothing in the input data marks an anomaly.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from . import config
from .schema import TABLES

VOCAB = json.loads((Path(__file__).resolve().parents[2] / "llm_cache" / "vocab.json").read_text(encoding="utf-8"))
EPOCH = pd.Timestamp(config.START) + pd.Timedelta(hours=6)
D, Y = config.DAYS, config.YEAR
H_END = D * 24
ROLE_IDS = np.array(["ROLE-01", "ROLE-02", "ROLE-03", "ROLE-04"], dtype=object)
ROLE_NAMES = ["Cashier", "Stock Associate", "Shift Supervisor", "Store Manager"]
PER_STORE = sum(config.STAFF.values())
ROLE_OFFSET = dict(zip(config.STAFF, np.cumsum([0] + list(config.STAFF.values())[:-1])))
WRITE_OFF_REASONS = ["DAMAGE", "EXPIRED", "MISCOUNT"]


# ---------- small helpers ----------
def ids(prefix, n, width):
    return np.array([f"{prefix}{i:0{width}d}" for i in range(1, n + 1)], dtype=object)


def rh(h):  # round to whole seconds so internal comparisons match the exported timestamps
    return np.round(np.asarray(h, dtype=float) * 3600) / 3600


def ts(h):
    return EPOCH + pd.to_timedelta(np.round(np.asarray(h, dtype=float) * 3600).astype("int64"), unit="s")


def day_str(days):
    return np.asarray((pd.Timestamp(config.START) + pd.to_timedelta(np.asarray(days), unit="D")).strftime("%Y-%m-%d"),
                      dtype=object)


def shift_of(store, h):
    return np.asarray(store) * D * 3 + (np.asarray(h) // 24).astype(int) * 3 + ((np.asarray(h) % 24) // 8).astype(int)


def shift_start_h(shift):
    return ((shift // 3) % D) * 24 + (shift % 3) * 8


def opt_ids(idx, idmap):
    idx = np.asarray(idx)
    out = np.full(len(idx), None, dtype=object)
    ok = idx >= 0
    out[ok] = idmap[idx[ok]]
    return out


def notes(w, reasons):
    reasons = np.asarray(reasons, dtype=object)
    out = np.full(len(reasons), None, dtype=object)
    for r in sorted(set(reasons)):   # sorted: set order changes between Python processes
        m = reasons == r
        out[m] = w.rng.choice(VOCAB["notes"][r], m.sum())
    return out


def part(w, store, sku, mtype, qty, h, col, **extra):
    """One block of movements. Shift and employee follow from store, time and role column."""
    h = rh(h)
    shift = shift_of(store, h)
    d = dict(store=np.asarray(store), sku=np.asarray(sku), type=mtype, qty=np.asarray(qty, dtype=int), h=h,
             shift=shift, emp=w.assign[shift, col], reason=None, note=None, transfer=-1, cp_store=-1,
             promo=-1, ret=-1, count=-1, tag="")
    d.update(extra)
    return pd.DataFrame(d)


def pair_of(w, store, sku):
    return np.searchsorted(w.pair_key, np.asarray(store) * w.K + np.asarray(sku))


# ---------- parent tables ----------
def make_stores(w):
    cities = VOCAB["cities"]
    c = w.rng.integers(0, len(cities), w.S)
    fmt = w.rng.choice(["HYPERMARKET", "SUPERMARKET", "EXPRESS"], w.S, p=[0.2, 0.5, 0.3])
    area = np.array([{"HYPERMARKET": 6000, "SUPERMARKET": 2500, "EXPRESS": 600}[f] for f in fmt])
    w.traffic = np.array([{"HYPERMARKET": 3.0, "SUPERMARKET": 1.5, "EXPRESS": 0.6}[f] for f in fmt])
    w.opened_days = -w.rng.integers(400, 5000, w.S)
    w.store_ids = ids("STORE-", w.S, 6)
    w.t["store"] = pd.DataFrame({
        "store_id": w.store_ids,
        "store_name": [f"{cities[i]['city']} {f.title()} {k + 1:03d}" for k, (i, f) in enumerate(zip(c, fmt))],
        "city": [cities[i]["city"] for i in c],
        "region": [cities[i]["region"] for i in c],
        "store_format": fmt,
        "sales_area_sqm": np.round(area * w.rng.uniform(0.8, 1.2, w.S)).astype(int),
        "opened_date": day_str(w.opened_days)})


def make_skus(w):
    combos = [(cat["name"], b, f"{b} {v} {it['name']} {s}", s, it["price"] * (1 + 0.6 * si) * (1 + 0.12 * vi),
               cat["perishable"], cat["shrink_risk"])
              for cat in VOCAB["categories"] for it in cat["items"] for b in cat["brands"]
              for vi, v in enumerate(cat["variants"]) for si, s in enumerate(it["sizes"])]
    assert len(combos) >= w.K, f"vocab gives {len(combos)} unique SKUs, need {w.K}"
    rows = [combos[i] for i in w.rng.choice(len(combos), w.K, replace=False)]
    w.price = np.round(np.array([r[4] for r in rows]) * w.rng.uniform(0.85, 1.2, w.K))
    w.cost = np.round(w.price * w.rng.uniform(0.6, 0.8, w.K), 2)
    w.perish = np.array([r[5] for r in rows])
    w.risk = np.array([r[6] for r in rows], dtype=object)
    w.pop = w.rng.lognormal(0, 1, w.K)
    w.sku_ids = ids("SKU-", w.K, 6)
    w.t["sku"] = pd.DataFrame({
        "sku_id": w.sku_ids, "sku_name": [r[2] for r in rows], "category": [r[0] for r in rows],
        "brand": [r[1] for r in rows], "pack_size": [r[3] for r in rows], "unit_cost_inr": w.cost,
        "unit_price_inr": w.price, "is_perishable": w.perish.astype(int), "shrink_risk": w.risk})


def make_staff(w):
    slot_role = np.concatenate([np.full(n, r) for r, n in config.STAFF.items()])
    w.emp_store = np.repeat(np.arange(w.S), PER_STORE)
    w.emp_role = np.tile(slot_role, w.S)
    n = len(w.emp_store)
    w.emp_ids = ids("EMP-", n, 6)
    open_d = w.opened_days[w.emp_store]
    hire = day_str(open_d + (w.rng.random(n) * (-open_d - 1)).astype(int))
    w.t["role"] = pd.DataFrame({"role_id": ROLE_IDS, "role_name": ROLE_NAMES, "can_post_adjustments": [0, 1, 1, 1]})
    w.t["employee"] = pd.DataFrame({
        "employee_id": w.emp_ids, "store_id": w.store_ids[w.emp_store],
        "first_name": w.rng.choice(VOCAB["first_names"], n), "last_name": w.rng.choice(VOCAB["last_names"], n),
        "hire_date": hire})
    sup = w.emp_role == 2
    w.t["employee_role"] = pd.concat([
        pd.DataFrame({"employee_id": w.emp_ids, "role_id": ROLE_IDS[w.emp_role], "effective_from": hire}),
        pd.DataFrame({"employee_id": w.emp_ids[sup], "role_id": "ROLE-02", "effective_from": hire[sup]}),
    ], ignore_index=True).assign(effective_to=None)


def make_shifts(w):
    n = w.S * D * 3
    i = np.arange(n)
    st, day, slot = i // (D * 3), (i // 3) % D, i % 3
    start = day * 24 + slot * 8
    w.shift_ids = ids(f"SHF-{Y}-", n, 6)
    w.t["shift"] = pd.DataFrame({
        "shift_id": w.shift_ids, "store_id": w.store_ids[st], "shift_date": day_str(day),
        "shift_type": np.array(["MORNING", "EVENING", "NIGHT"], dtype=object)[slot],
        "start_ts": ts(start), "end_ts": ts(start + 8)})
    # 3 people per shift: column 0 cashier, 1 stock associate, 2 supervisor
    w.assign = np.stack([st * PER_STORE + ROLE_OFFSET[c] + w.rng.integers(0, config.STAFF[c], n)
                         for c in range(3)], axis=1)
    w.t["shift_assignment"] = pd.DataFrame({
        "shift_id": np.repeat(w.shift_ids, 3), "employee_id": w.emp_ids[w.assign.ravel()],
        "role_id": ROLE_IDS[np.tile([0, 1, 2], n)]})


def make_assortment(w):
    k = max(2, round(config.ASSORTMENT_FRAC * w.K))
    p = w.pop / w.pop.sum()
    w.carries = np.zeros((w.S, w.K), dtype=bool)
    for s in range(w.S):
        w.carries[s, w.rng.choice(w.K, k, replace=False, p=p)] = True
    w.ps, w.pk = np.nonzero(w.carries)
    w.pair_key = w.ps * w.K + w.pk
    w.n_pairs = len(w.ps)
    pw = w.pop[w.pk] * w.traffic[w.ps]
    w.pw = pw / pw.sum()


def make_promotions(w, n_pr):
    start = np.sort(w.rng.integers(0, D - 21, n_pr))
    end = start + w.rng.integers(7, 22, n_pr) - 1
    w.promo_disc = w.rng.choice([10, 15, 20, 25, 30], n_pr)
    w.promo_ids = ids(f"PRM-{Y}-", n_pr, 4)
    w.t["promotion"] = pd.DataFrame({
        "promotion_id": w.promo_ids,
        "promotion_name": [f"{t} #{i + 1}" for i, t in enumerate(w.rng.choice(VOCAB["promotion_themes"], n_pr))],
        "start_date": day_str(start), "end_date": day_str(end), "discount_pct": w.promo_disc})
    lo, hi = max(2, round(0.004 * w.K)), max(3, round(0.03 * w.K))
    rows = [(p, s) for p in range(n_pr) for s in w.rng.choice(w.K, w.rng.integers(lo, hi), replace=False)]
    psk = pd.DataFrame(rows, columns=["promo", "sku"])
    w.t["promotion_sku"] = pd.DataFrame({"promotion_id": w.promo_ids[psk.promo], "sku_id": w.sku_ids[psk.sku]})
    return psk.assign(sd=start[psk.promo], ed=end[psk.promo])


# ---------- clean baseline (exactly cfg['movements'] rows) ----------
def baseline(w, cfg):
    rng, N = w.rng, cfg["movements"]
    n_tr = round(N * config.MIX["transfer_pairs"])
    lost = rng.random(n_tr) < config.TRANSIT_LOSS_RATE
    n_ret = round(N * config.MIX["returns"])
    dmg = rng.random(n_ret) < config.DAMAGED_RETURN_RATE
    n_adj, n_rec = round(N * config.MIX["adjustments"]), round(N * config.MIX["receipts"])
    n_sale = N - (2 * n_tr + lost.sum() + n_ret + dmg.sum() + n_adj + n_rec)
    psk = make_promotions(w, cfg["promotions"])

    # sales (first block, so a sale's row number is its uid)
    p = rng.choice(w.n_pairs, n_sale, p=w.pw)
    day = rng.integers(0, D, n_sale)
    sales = part(w, w.ps[p], w.pk[p], "SALE", -np.minimum(rng.geometric(0.6, n_sale), 6),
                 day * 24 + 1 + 16 * rng.beta(2, 2, n_sale), 0)
    s = pd.DataFrame({"row": np.arange(n_sale), "sku": sales.sku, "day": day}).merge(psk, on="sku")
    s = s[(s.day >= s.sd) & (s.day <= s.ed)].sort_values(["row", "promo"]).drop_duplicates("row")
    sales.loc[s.row.values, "promo"] = s.promo.values

    # receipts: case packs, mostly in the morning
    p = rng.choice(w.n_pairs, n_rec, p=w.pw)
    receipts = part(w, w.ps[p], w.pk[p], "RECEIPT", rng.choice([6, 12, 24], n_rec, p=[0.4, 0.4, 0.2]),
                    rng.integers(0, D, n_rec) * 24 + rng.uniform(0, 6, n_rec), 1)

    # transfers between two stores that both stock the SKU
    elig = w.carries.sum(0)[w.pk] >= 2
    pe = w.pw * elig
    p = rng.choice(w.n_pairs, n_tr, p=pe / pe.sum())
    src, sku = w.ps[p], w.pk[p]
    cand = w.carries[:, sku].T.copy()
    cand[np.arange(n_tr), src] = False
    dst = (rng.random(cand.shape) * cand).argmax(1)
    out_h = rh(rng.integers(0, D - 4, n_tr) * 24 + rng.uniform(2, 10, n_tr))
    in_h = rh(out_h + rng.uniform(20, 72, n_tr))
    q = rng.integers(4, 21, n_tr)
    t = np.arange(n_tr)
    w.tr = pd.DataFrame({"sku": sku, "src": src, "dst": dst, "qty": q, "out_h": out_h, "in_h": in_h, "lost": lost})
    tr_out = part(w, src, sku, "TRANSFER_OUT", -q, out_h, 1, transfer=t, cp_store=dst)
    tr_in = part(w, dst, sku, "TRANSFER_IN", q, in_h, 1, transfer=t, cp_store=src)
    tr_loss = part(w, dst[lost], sku[lost], "ADJUSTMENT", -q[lost], in_h[lost] + 0.5, 1, reason="TRANSIT_LOSS",
                   note=notes(w, ["TRANSIT_LOSS"] * lost.sum()), transfer=t[lost], cp_store=src[lost])

    # customer returns, each tied to an earlier sale; damaged ones are written off right after
    rs = rng.choice(n_sale, n_ret, replace=False)
    sale_h, sold = sales.h.values[rs], -sales.qty.values[rs]
    ret_h = sale_h + rng.uniform(1, 14 * 24, n_ret)
    over = ret_h >= H_END - 1
    ret_h[over] = sale_h[over] + rng.uniform(0.5, 1.0, over.sum())
    rq = 1 + (rng.random(n_ret) * sold).astype(int)
    rstore, rsku = sales.store.values[rs], sales.sku.values[rs]
    reason = np.where(dmg, np.where(w.perish[rsku], "EXPIRED_AT_PURCHASE", "DEFECTIVE"),
                      rng.choice(["CHANGED_MIND", "WRONG_ITEM"], n_ret, p=[0.65, 0.35]))
    r = np.arange(n_ret)
    w.ret = pd.DataFrame({"sale_uid": rs, "store": rstore, "sku": rsku, "qty": rq, "h": rh(ret_h), "reason": reason,
                          "cond": np.where(dmg, "DAMAGED", "RESALEABLE"), "promo": sales.promo.values[rs]})
    returns = part(w, rstore, rsku, "RETURN", rq, ret_h, 0, ret=r)
    dmg_adj = part(w, rstore[dmg], rsku[dmg], "ADJUSTMENT", -rq[dmg], ret_h[dmg] + 0.25, 2,
                   reason="DAMAGED_RETURN", note=notes(w, ["DAMAGED_RETURN"] * dmg.sum()), ret=r[dmg])

    # everyday adjustments: damage, expiry, miscounts, found stock
    p = rng.choice(w.n_pairs, n_adj, p=w.pw)
    asku = w.pk[p]
    reason = rng.choice(["DAMAGE", "EXPIRED", "MISCOUNT", "FOUND"], n_adj, p=[0.4, 0.25, 0.25, 0.1]).astype(object)
    reason[(reason == "EXPIRED") & ~w.perish[asku]] = "DAMAGE"
    mag = np.where(reason == "EXPIRED", rng.integers(1, 7, n_adj), rng.integers(1, 4, n_adj))
    mag = np.where(np.isin(reason, ["MISCOUNT", "FOUND"]), rng.integers(1, 3, n_adj), mag)
    sign = np.where(reason == "FOUND", 1, np.where(reason == "MISCOUNT", np.where(rng.random(n_adj) < 0.6, -1, 1), -1))
    adj = part(w, w.ps[p], asku, "ADJUSTMENT", sign * mag, rng.integers(0, D, n_adj) * 24 + rng.uniform(0, 24, n_adj),
               np.where(rng.random(n_adj) < 0.7, 1, 2), reason=reason, note=notes(w, reason))

    mov = pd.concat([sales, receipts, tr_out, tr_in, tr_loss, returns, dmg_adj, adj], ignore_index=True)
    assert len(mov) == N
    return mov


def baseline_counts(w, n_c):
    rng = w.rng
    pick = rng.choice(w.n_pairs * (D - 7), n_c, replace=False)   # unique (store, sku, day)
    cp, cday = pick % w.n_pairs, 7 + pick // w.n_pairs
    as_of = rh(cday * 24 + rng.uniform(0, 1.5, n_c))             # book frozen 06:00-07:30
    store, sku = w.ps[cp], w.pk[cp]
    shift = shift_of(store, as_of)
    u = rng.random(n_c)
    var = np.where(u < 0.10, -rng.integers(1, 3, n_c), np.where(u < 0.13, rng.integers(1, 3, n_c), 0))
    tail_p = np.select([w.risk[sku] == "HIGH", w.risk[sku] == "MEDIUM"], [0.03, 0.01], 0.005)
    var = np.where(rng.random(n_c) < tail_p, -rng.integers(3, 8, n_c), var)   # honest, untraceable shrink
    return pd.DataFrame({"pair": cp, "store": store, "sku": sku, "as_of": as_of,
                         "h": rh(as_of + rng.uniform(0.05, 0.5, n_c)), "var": var,
                         "emp": w.assign[shift, 2], "shift": shift, "tag": ""})


def last_handler(mov, counts):
    """Last movement (not a count correction) on the same store+SKU at or before each count's book time."""
    right = mov.loc[mov.reason.ne("COUNT_VARIANCE") | mov.reason.isna(), ["pair", "h", "emp"]]
    right = right.sort_values("h", kind="stable").rename(columns={"h": "last_h", "emp": "last_emp"})
    left = counts[["pair", "as_of"]].reset_index().sort_values("as_of", kind="stable")
    j = pd.merge_asof(left, right, left_on="as_of", right_on="last_h", by="pair", direction="backward")
    return j.set_index("index").sort_index()


# ---------- planted problems ----------
def inject(w, mov, counts, inj):
    rng, gt, new = w.rng, [], []
    base = mov.tag.eq("")
    perm = rng.permutation(w.S)
    k_rep, k_dec, k_un = inj["repeated_adjusters"], inj["damage_event_stores"], inj["unexplained_loss_employees"]
    rep_stores, dec_stores, un_stores = perm[:k_rep], perm[k_rep:k_rep + k_dec], perm[k_rep + k_dec:k_rep + k_dec + k_un]

    # 1. movement points to the wrong store: receipt booked to another store, shift/employee still the real store
    cand = np.flatnonzero(base & mov.type.eq("RECEIPT") & (w.carries.sum(0)[mov.sku] >= 2))
    for i, r in enumerate(rng.choice(cand, inj["wrong_store"], replace=False)):
        others = np.flatnonzero(w.carries[:, mov.at[r, "sku"]])
        true_store = mov.at[r, "store"]
        mov.at[r, "store"] = rng.choice(others[others != true_store])
        mov.at[r, "tag"] = tag = f"wrong_store#{i}"
        gt.append(dict(tag=tag, type="WRONG_STORE", entity="MOVEMENT", true_store=true_store))

    # 2. adjustment with no reason
    cand = np.flatnonzero(base & mov.type.eq("ADJUSTMENT") & mov.reason.isin(WRITE_OFF_REASONS))
    for i, r in enumerate(rng.choice(cand, inj["missing_reason"], replace=False)):
        old = mov.at[r, "reason"]
        mov.loc[r, ["reason", "note"]] = None
        mov.at[r, "tag"] = tag = f"missing_reason#{i}"
        gt.append(dict(tag=tag, type="MISSING_REASON", entity="MOVEMENT", old_reason=old))

    # 3. transfer counted as a loss at both stores: sender also writes off a transfer the receiver already wrote off
    lost = np.flatnonzero(w.tr.lost.values)
    for i, t in enumerate(rng.choice(lost, min(inj["transfer_double_loss"], len(lost)), replace=False)):
        tr = w.tr.iloc[t]
        tag = f"transfer_double_loss#{i}"
        new.append(part(w, [tr.src], [tr.sku], "ADJUSTMENT", [-tr.qty], [tr.in_h + rng.uniform(1, 24)], 1,
                        reason="TRANSIT_LOSS", note=notes(w, ["TRANSIT_LOSS"]), transfer=t, cp_store=tr.dst, tag=tag))
        gt.append(dict(tag=tag, type="TRANSFER_DOUBLE_LOSS", entity="TRANSFER", transfer=t))

    # 4. DECOY: one-day damage incident -- innocent, must not be called theft. The morning stock associate
    #    logs most of the clean-up, so counted per person it looks just like the repeated-adjustment pattern.
    for i, s in enumerate(dec_stores):
        d, tag = rng.integers(10, D - 10), f"decoy_damage_event#{i}"
        skus = np.flatnonzero(w.carries[s])
        wt = 1 + 3 * w.perish[skus]          # perishables spoil more in an incident
        note = rng.choice(VOCAB["notes"]["DAMAGE_EVENT"])
        for slot, (lo, hi, p_assoc) in enumerate([(30, 45, 0.85), (8, 13, 0.5), (4, 8, 0.5)]):
            n = rng.integers(lo, hi)
            sk = rng.choice(skus, n, p=wt / wt.sum())
            new.append(part(w, np.full(n, s), sk, "ADJUSTMENT", -rng.integers(1, 7, n),
                            d * 24 + slot * 8 + rng.uniform(0.2, 7.8, n), np.where(rng.random(n) < p_assoc, 1, 2),
                            reason=np.where(w.perish[sk], "EXPIRED", "DAMAGE").astype(object), note=note, tag=tag))
        gt.append(dict(tag=tag, type="DECOY_DAMAGE_EVENT", entity="STORE_DAY", store=s, day=d, label="DECOY"))

    # 5. repeated adjustments: one stock associate writes off far more than peers, mostly on night shifts
    is_wo = mov.type.eq("ADJUSTMENT") & mov.reason.isin(WRITE_OFF_REASONS) & mov.qty.lt(0)
    for i, s in enumerate(rep_stores):
        e = s * PER_STORE + ROLE_OFFSET[1] + rng.integers(0, config.STAFF[1])
        normal = int((is_wo & mov.emp.eq(e)).sum())
        m = max(8, round(config.REPEATED_ADJ_MULTIPLIER * normal))
        sh = np.flatnonzero(w.assign[:, 1] == e)
        night = sh[sh % 3 == 2]
        n_night = round(0.75 * m) if len(night) else 0
        shifts = np.concatenate([rng.choice(night, n_night), rng.choice(sh, m - n_night)]) if n_night else rng.choice(sh, m)
        skus = np.flatnonzero(w.carries[s])
        wt = w.cost[skus] * np.where(w.risk[skus] == "HIGH", 3, 1)
        sk = rng.choice(skus, m, p=wt / wt.sum())
        reason = rng.choice(["DAMAGE", "MISCOUNT"], m, p=[0.6, 0.4]).astype(object)
        tag = f"repeated_adjustments#{i}"
        new.append(part(w, np.full(m, s), sk, "ADJUSTMENT", -rng.integers(1, 4, m),
                        shift_start_h(shifts) + rng.uniform(0.2, 7.8, m), 1, reason=reason, note=notes(w, reason), tag=tag))
        gt.append(dict(tag=tag, type="REPEATED_ADJUSTMENTS", entity="EMPLOYEE", emp=e, normal=normal, extra=m))

    mov = pd.concat([mov] + new, ignore_index=True)
    mov["pair"] = pair_of(w, mov.store.values, mov.sku.values)
    counts = counts.copy()
    lh = last_handler(mov, counts)

    # 6. count timestamped before movements it already includes (book frozen later than the count)
    cand = np.flatnonzero(counts.tag.eq("") & (counts.as_of - lh.last_h < 72).fillna(False).values)
    for i, c in enumerate(rng.choice(cand, inj["count_before_movements"], replace=False)):
        counts.at[c, "h"] = max(0.01, float(rh(lh.at[c, "last_h"] - rng.uniform(0.1, 2.0))))
        counts.at[c, "tag"] = tag = f"count_before_movements#{i}"
        gt.append(dict(tag=tag, type="COUNT_BEFORE_MOVEMENTS", entity="CYCLE_COUNT"))

    # 7. unexplained loss: big shortages on stock last handled by one employee
    for i, s in enumerate(un_stores):
        ok = counts.tag.eq("").values & (counts.store.values == s) & lh.last_emp.notna().values
        vc = lh.last_emp[ok].astype(int).value_counts()
        need = inj["unexplained_counts_each"]
        e = rng.choice(vc.index[vc >= need].to_numpy()) if (vc >= need).any() else vc.index[0]
        rows = np.flatnonzero(ok & (lh.last_emp.values == e))
        rows = rng.choice(rows, min(need, len(rows)), replace=False)
        tag = f"unexplained_loss#{i}"
        counts.loc[rows, "var"] = -rng.integers(*config.UNEXPLAINED_SHORTAGE, len(rows))
        counts.loc[rows, "tag"] = tag
        gt.append(dict(tag=tag, type="UNEXPLAINED_LOSS", entity="EMPLOYEE", emp=int(e)))
    return mov, counts, gt


# ---------- balances from the data ----------
def finish_counts(w, mov, counts):
    """Post count variances as new movements, then derive opening stock and expected/counted quantities."""
    nz = counts["var"].ne(0).values
    c = counts[nz]
    corr = part(w, c.store.values, c.sku.values, "ADJUSTMENT", c["var"].values,
                np.maximum(c.h.values, c.as_of.values) + 5 / 60, 2, reason="COUNT_VARIANCE",
                note=notes(w, ["COUNT_VARIANCE"] * nz.sum()), count=np.flatnonzero(nz))
    mov = pd.concat([mov, corr], ignore_index=True)
    mov["pair"] = pair_of(w, mov.store.values, mov.sku.values)

    srt = mov.sort_values(["pair", "h"], kind="stable")
    cum = srt.groupby("pair").qty.cumsum()
    need_run = (-cum.groupby(srt.pair).min()).clip(lower=0).reindex(range(w.n_pairs), fill_value=0).values
    right = pd.DataFrame({"pair": srt.pair.values, "h": srt.h.values, "cum": cum.values}).sort_values("h", kind="stable")
    left = counts[["pair", "as_of"]].reset_index().sort_values("as_of", kind="stable")
    j = pd.merge_asof(left, right, left_on="as_of", right_on="h", by="pair", direction="backward")
    cum_asof = j.set_index("index").sort_index().cum.fillna(0).astype(int).values
    need_cnt = (pd.Series(-(cum_asof + counts["var"].values)).groupby(counts.pair.values).max()
                .clip(lower=0).reindex(range(w.n_pairs), fill_value=0).values)
    w.opening = np.maximum.reduce([w.rng.integers(5, 40, w.n_pairs), need_run, need_cnt]) + w.rng.integers(0, 4, w.n_pairs)
    counts = counts.assign(expected=w.opening[counts.pair.values] + cum_asof)
    counts["counted"] = counts.expected + counts["var"]
    w.closing = w.opening + mov.groupby("pair").qty.sum().reindex(range(w.n_pairs), fill_value=0).values
    return mov, counts


# ---------- IDs and export tables ----------
def build_tables(w, mov, counts):
    t = w.t
    mov = mov.sort_values(["h", "pair", "type", "qty"], kind="stable").reset_index(drop=True)
    w.mov_ids = ids(f"MOV-{Y}-", len(mov), 8)
    mid_of_uid = np.empty(len(mov), dtype=object)
    mid_of_uid[mov.uid.values] = w.mov_ids

    tr_order = np.argsort(w.tr.out_h.values, kind="stable")
    w.tr_ids = np.empty(len(tr_order), dtype=object)
    w.tr_ids[tr_order] = ids(f"TRF-{Y}-", len(tr_order), 6)
    ret_order = np.argsort(w.ret.h.values, kind="stable")
    w.ret_ids = np.empty(len(ret_order), dtype=object)
    w.ret_ids[ret_order] = ids(f"RET-{Y}-", len(ret_order), 6)
    cnt_order = np.lexsort((counts.pair.values, counts.as_of.values))
    w.cnt_ids = np.empty(len(counts), dtype=object)
    w.cnt_ids[cnt_order] = ids(f"CNT-{Y}-", len(counts), 6)

    t["store_sku"] = pd.DataFrame({"store_id": w.store_ids[w.ps], "sku_id": w.sku_ids[w.pk], "opening_qty": w.opening,
                                   "opening_date": config.START, "closing_book_qty": w.closing})
    tr = w.tr
    t["transfer"] = pd.DataFrame({
        "transfer_id": w.tr_ids, "sku_id": w.sku_ids[tr.sku], "from_store_id": w.store_ids[tr.src],
        "to_store_id": w.store_ids[tr.dst], "quantity": tr.qty, "shipped_ts": ts(tr.out_h), "received_ts": ts(tr.in_h),
        "status": np.where(tr.lost, "LOST_IN_TRANSIT", "RECEIVED")}).iloc[tr_order]
    t["inventory_movement"] = pd.DataFrame({
        "movement_id": w.mov_ids, "movement_ts": ts(mov.h), "store_id": w.store_ids[mov.store],
        "sku_id": w.sku_ids[mov.sku], "movement_type": mov["type"].values, "quantity": mov.qty.values,
        "unit_cost_inr": w.cost[mov.sku], "reason_code": mov.reason.values, "note": mov.note.values,
        "employee_id": w.emp_ids[mov.emp], "shift_id": w.shift_ids[mov["shift"].values],
        "transfer_id": opt_ids(mov.transfer.values, w.tr_ids), "counterparty_store_id": opt_ids(mov.cp_store.values, w.store_ids),
        "promotion_id": opt_ids(mov.promo.values, w.promo_ids), "return_id": opt_ids(mov.ret.values, w.ret_ids),
        "count_id": opt_ids(mov["count"].values, w.cnt_ids)})
    r = w.ret
    disc = np.where(r.promo.values >= 0, w.promo_disc[np.maximum(r.promo.values, 0)], 0)
    t["customer_return"] = pd.DataFrame({
        "return_id": w.ret_ids, "original_sale_movement_id": mid_of_uid[r.sale_uid.values],
        "store_id": w.store_ids[r.store], "sku_id": w.sku_ids[r.sku], "quantity": r.qty, "return_ts": ts(r.h),
        "return_reason": r.reason, "item_condition": r.cond,
        "refund_amount_inr": np.round(r.qty.values * w.price[r.sku] * (1 - disc / 100), 2)}).iloc[ret_order]
    c = counts
    t["cycle_count"] = pd.DataFrame({
        "count_id": w.cnt_ids, "store_id": w.store_ids[c.store], "sku_id": w.sku_ids[c.sku],
        "system_qty_as_of_ts": ts(c.as_of), "count_ts": ts(c.h), "expected_qty": c.expected, "counted_qty": c.counted,
        "variance_qty": c["var"], "variance_value_inr": np.round(c["var"].values * w.cost[c.sku], 2),
        "employee_id": w.emp_ids[c.emp], "shift_id": w.shift_ids[c["shift"].values]}).iloc[cnt_order]
    for name in t:   # fixed column order and row order -> stable checksums
        t[name] = t[name][[col["name"] for col in TABLES[name]["cols"]]].reset_index(drop=True)
    return mov


def ground_truth(w, mov, counts, gt):
    rows = []
    for g in gt:
        m = mov[mov.tag.eq(g["tag"])]
        mids = w.mov_ids[m.index.values]
        label, emp, related = g.get("label", "ANOMALY"), None, ""
        if g["type"] == "WRONG_STORE":
            r = m.iloc[0]
            eid, store = mids[0], w.store_ids[r.store]
            emp, related = w.emp_ids[r.emp], w.shift_ids[r["shift"]]
            desc = (f"Receipt of {r.qty} units booked to {store}, but its shift {related} and employee {emp} "
                    f"belong to {w.store_ids[g['true_store']]}.")
        elif g["type"] == "MISSING_REASON":
            r = m.iloc[0]
            eid, store, emp = mids[0], w.store_ids[r.store], w.emp_ids[r.emp]
            desc = f"Reason '{g['old_reason']}' removed from a {r.qty}-unit adjustment."
        elif g["type"] == "TRANSFER_DOUBLE_LOSS":
            tr = w.tr.iloc[g["transfer"]]
            eid, store = w.tr_ids[g["transfer"]], w.store_ids[tr.src]
            both = mov.index[mov.transfer.eq(g["transfer"]) & mov.reason.eq("TRANSIT_LOSS")]
            related = ";".join(w.mov_ids[both])
            desc = (f"Transfer of {tr.qty} units lost in transit was written off by the receiver "
                    f"{w.store_ids[tr.dst]} and again by the sender {store}.")
        elif g["type"] == "DECOY_DAMAGE_EVENT":
            store = w.store_ids[g["store"]]
            eid, related = f"{store}|{day_str([g['day']])[0]}", ";".join(mids)
            desc = f"Innocent one-day incident: {len(m)} reasoned write-offs ({m.note.iloc[0]})."
        elif g["type"] == "REPEATED_ADJUSTMENTS":
            eid = emp = w.emp_ids[g["emp"]]
            store, related = w.store_ids[w.emp_store[g["emp"]]], ";".join(mids)
            night = np.mean(m["shift"].values % 3 == 2)
            desc = (f"{g['extra']} extra small write-offs ({night:.0%} on night shifts, high-value SKUs) "
                    f"on top of {g['normal']} normal ones.")
        elif g["type"] == "COUNT_BEFORE_MOVEMENTS":
            c = counts[counts.tag.eq(g["tag"])].iloc[0]
            eid, store, emp = w.cnt_ids[c.name], w.store_ids[c.store], w.emp_ids[c.emp]
            desc = f"count_ts set {c.as_of - c.h:.1f} h before system_qty_as_of_ts; movements in between are in expected_qty."
        elif g["type"] == "UNEXPLAINED_LOSS":
            c = counts[counts.tag.eq(g["tag"])]
            eid = emp = w.emp_ids[g["emp"]]
            store, related = w.store_ids[w.emp_store[g["emp"]]], ";".join(w.cnt_ids[c.index.values])
            desc = f"{len(c)} counts given shortages of {-c['var'].sum()} units in total; this employee last handled the stock."
        rows.append(dict(anomaly_type=g["type"], label=label, entity_type=g["entity"], entity_id=eid, store_id=store,
                         employee_id=emp, related_ids=related, description=desc))
    out = pd.DataFrame(rows)
    out.insert(0, "gt_id", [f"GT-{i:04d}" for i in range(1, len(out) + 1)])
    return out


def generate(size="small"):
    cfg = config.SIZES[size]
    w = SimpleNamespace(rng=np.random.default_rng(config.SEED), S=cfg["stores"], K=cfg["skus"], t={})
    make_stores(w); make_skus(w); make_staff(w); make_shifts(w); make_assortment(w)
    mov = baseline(w, cfg)
    counts = baseline_counts(w, cfg["counts"])
    mov, counts, gt = inject(w, mov, counts, cfg["inject"])
    mov, counts = finish_counts(w, mov, counts)
    mov["uid"] = np.arange(len(mov))
    mov = build_tables(w, mov, counts)
    return w.t, ground_truth(w, mov, counts, gt)
