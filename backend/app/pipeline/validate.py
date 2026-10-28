"""Data checks. 'integrity' checks must all pass; 'business_rule' checks are expected to catch
exactly the planted data errors (they are reported, not failed)."""
import re

import pandas as pd

from .schema import TABLES

H8 = pd.Timedelta(hours=8)


def key(df, cols):
    return df[cols[0]].astype(str) if len(cols) == 1 else df[cols].astype(str).agg("|".join, axis=1)


def validate(t):
    res = []

    def check(name, bad, category="integrity", detail=""):
        n = int(bad.sum()) if hasattr(bad, "sum") else int(bad)
        status = "PASS" if n == 0 else ("FAIL" if category == "integrity" else "FLAGGED")
        res.append(dict(check=name, category=category, status=status, failing_rows=n, detail=detail))

    # --- structure: keys, formats, required, allowed values, foreign keys ---
    for name, spec in TABLES.items():
        if name not in t:
            continue
        df = t[name]
        check(f"{name}: primary key unique", df.duplicated(spec["pk"]))
        if spec.get("id"):
            check(f"{name}: id format {spec['id']}", ~df[spec["pk"][0]].astype(str).str.fullmatch(spec["id"]))
        for c in spec["cols"]:
            if c["required"]:
                check(f"{name}.{c['name']}: required", df[c["name"]].isna())
            if c["allowed"]:
                v = df[c["name"]].dropna()
                check(f"{name}.{c['name']}: allowed values", ~v.isin(c["allowed"]))
        for a, rt, b in spec["fks"]:
            if rt not in t:
                continue
            child = df.dropna(subset=a)
            check(f"{name}.{'+'.join(a)} -> {rt}: foreign key", ~key(child, a).isin(set(key(t[rt], b))))

    mv, sh, cc = t["inventory_movement"], t["shift"], t["cycle_count"]
    st, sk, ss = t["store"], t["sku"], t["store_sku"]

    # --- dates in the right order ---
    check("shift: end = start + 8h", sh.end_ts - sh.start_ts != H8)
    pr = t["promotion"]
    check("promotion: end_date >= start_date", pr.end_date < pr.start_date)
    tr = t["transfer"]
    check("transfer: received after shipped", tr.received_ts <= tr.shipped_ts)
    check("transfer: two different stores", tr.from_store_id == tr.to_store_id)
    emp = t["employee"].merge(st[["store_id", "opened_date"]], on="store_id")
    check("employee: hired on/after store opened", emp.hire_date < emp.opened_date)
    m = mv[["movement_ts", "shift_id"]].merge(sh[["shift_id", "start_ts", "end_ts"]], on="shift_id")
    check("movement: timestamp inside its shift", (m.movement_ts < m.start_ts) | (m.movement_ts >= m.end_ts))
    m = cc[["system_qty_as_of_ts", "shift_id"]].merge(sh[["shift_id", "start_ts", "end_ts"]], on="shift_id")
    check("cycle_count: book time inside its shift", (m.system_qty_as_of_ts < m.start_ts) | (m.system_qty_as_of_ts >= m.end_ts))
    r = t["customer_return"].merge(mv[["movement_id", "movement_ts", "store_id", "sku_id", "quantity", "movement_type",
                                       "promotion_id"]], left_on="original_sale_movement_id", right_on="movement_id",
                                   suffixes=("", "_sale"))
    check("return: original movement is a SALE", r.movement_type != "SALE")
    check("return: after the sale", r.return_ts <= r.movement_ts)
    check("return: same store and SKU as the sale", (r.store_id != r.store_id_sale) | (r.sku_id != r.sku_id_sale))
    check("return: qty between 1 and units sold", (r.quantity < 1) | (r.quantity > -r.quantity_sale))

    # --- quantities and calculated fields ---
    pos, neg = ["RECEIPT", "TRANSFER_IN", "RETURN"], ["SALE", "TRANSFER_OUT"]
    check("movement: quantity sign matches type", (mv.movement_type.isin(pos) & (mv.quantity <= 0))
          | (mv.movement_type.isin(neg) & (mv.quantity >= 0)) | (mv.quantity == 0))
    check("movement: reason only on adjustments", mv.reason_code.notna() & (mv.movement_type != "ADJUSTMENT"))
    check("movement: unit cost matches SKU", mv[["sku_id", "unit_cost_inr"]].merge(sk[["sku_id", "unit_cost_inr"]], on="sku_id")
          .pipe(lambda d: d.unit_cost_inr_x != d.unit_cost_inr_y))
    check("movement: no duplicate rows (all fields except id)", mv.drop(columns="movement_id").duplicated())
    check("sku: price above cost", sk.unit_price_inr <= sk.unit_cost_inr)
    c = cc.merge(sk[["sku_id", "unit_cost_inr"]], on="sku_id")
    check("cycle_count: variance = counted - expected", c.variance_qty != c.counted_qty - c.expected_qty)
    check("cycle_count: variance value = variance x cost", (c.variance_value_inr - (c.variance_qty * c.unit_cost_inr).round(2)).abs() > 0.005)
    check("cycle_count: counted_qty >= 0", cc.counted_qty < 0)
    disc = mv.set_index("movement_id").promotion_id.map(pr.set_index("promotion_id").discount_pct).fillna(0)
    rr = r.merge(sk[["sku_id", "unit_price_inr"]], on="sku_id")
    want = (rr.quantity * rr.unit_price_inr * (1 - rr.original_sale_movement_id.map(disc) / 100)).round(2)
    check("return: refund = qty x price x (1 - discount)", (rr.refund_amount_inr - want).abs() > 0.005)
    corr = mv[mv.reason_code.eq("COUNT_VARIANCE")]
    cv = cc[cc.variance_qty != 0].merge(corr[["count_id", "quantity"]], on="count_id", how="left")
    check("cycle_count: every variance posted once as COUNT_VARIANCE", (cv.quantity != cv.variance_qty)
          | cv.duplicated("count_id", keep=False))

    # --- stock equation, recomputed independently of the generator ---
    ev = pd.concat([mv[["store_id", "sku_id", "movement_ts", "quantity"]].assign(o=0),
                    cc[["store_id", "sku_id", "system_qty_as_of_ts", "count_id"]]
                    .rename(columns={"system_qty_as_of_ts": "movement_ts"}).assign(quantity=0, o=1)], ignore_index=True)
    ev = ev.sort_values(["store_id", "sku_id", "movement_ts", "o"], kind="stable")
    ev["bal"] = ev.groupby(["store_id", "sku_id"]).quantity.cumsum()
    ev = ev.merge(ss[["store_id", "sku_id", "opening_qty"]], on=["store_id", "sku_id"], how="left")
    ev["bal"] += ev.opening_qty
    got = ev[ev.o == 1].set_index("count_id").bal
    check("stock equation: expected_qty = opening + movements up to book time",
          cc.set_index("count_id").expected_qty != got.reindex(cc.count_id).values,
          detail="opening + receipts - sales + transfers in - transfers out + adjustments + returns")
    check("stock: running balance never negative", ev.bal[ev.o == 0] < 0)
    tot = mv.groupby(["store_id", "sku_id"]).quantity.sum()
    s2 = ss.set_index(["store_id", "sku_id"])
    check("stock equation: closing = opening + all movements",
          s2.closing_book_qty != s2.opening_qty + tot.reindex(s2.index, fill_value=0))

    by = mv.groupby("movement_type").quantity.sum()
    adj = mv[mv.movement_type == "ADJUSTMENT"].groupby("reason_code", dropna=False).quantity.sum()
    eq = {"opening": int(ss.opening_qty.sum()), "receipts": int(by.get("RECEIPT", 0)), "sales": int(by.get("SALE", 0)),
          "transfers_in": int(by.get("TRANSFER_IN", 0)), "transfers_out": int(by.get("TRANSFER_OUT", 0)),
          "returns": int(by.get("RETURN", 0)), "adjustments": int(by.get("ADJUSTMENT", 0)),
          "adjustments_by_reason": {str(k) if pd.notna(k) else "MISSING": int(v) for k, v in adj.items()},
          "closing_book": int(ss.closing_book_qty.sum())}
    eq["balances"] = eq["opening"] + sum(eq[k] for k in ["receipts", "sales", "transfers_in", "transfers_out",
                                                          "returns", "adjustments"]) == eq["closing_book"]

    # --- business rules: these should flag exactly the planted data errors ---
    m = mv[["store_id", "shift_id"]].merge(sh[["shift_id", "store_id"]], on="shift_id", suffixes=("", "_shift"))
    check("movement store = its shift's store", m.store_id != m.store_id_shift, "business_rule")
    check("adjustment has a reason", (mv.movement_type == "ADJUSTMENT") & mv.reason_code.isna(), "business_rule")
    check("count_ts not before system_qty_as_of_ts", cc.count_ts < cc.system_qty_as_of_ts, "business_rule")
    tl = mv[mv.reason_code.eq("TRANSIT_LOSS")]
    check("transfer written off at most once", tl.duplicated("transfer_id"), "business_rule")

    return {"row_counts": {k: len(v) for k, v in t.items()},
            "integrity_passed": all(r["status"] == "PASS" for r in res if r["category"] == "integrity"),
            "stock_equation_totals": eq, "checks": res}

