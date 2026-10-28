"""Single source of truth for every table: columns, keys, allowed values.

validate.py checks data against it, run.py builds the SQLite DB from it, and
`python -m app.pipeline.schema` regenerates schema.sql and data_dictionary.md.
"""
from pathlib import Path

REGIONS = ["North", "South", "East", "West", "Central"]
FORMATS = ["HYPERMARKET", "SUPERMARKET", "EXPRESS"]
CATEGORIES = ["Fresh Produce", "Dairy", "Bakery", "Beverages", "Snacks", "Household", "Personal Care",
              "Electronics Accessories", "Apparel Basics", "Health & Pharmacy"]
RISK = ["LOW", "MEDIUM", "HIGH"]
ROLE_NAMES = ["Cashier", "Stock Associate", "Shift Supervisor", "Store Manager"]
SHIFT_TYPES = ["MORNING", "EVENING", "NIGHT"]
MOVEMENT_TYPES = ["RECEIPT", "SALE", "TRANSFER_OUT", "TRANSFER_IN", "ADJUSTMENT", "RETURN"]
REASONS = ["DAMAGE", "EXPIRED", "MISCOUNT", "FOUND", "DAMAGED_RETURN", "TRANSIT_LOSS", "COUNT_VARIANCE"]
RETURN_REASONS = ["DEFECTIVE", "CHANGED_MIND", "WRONG_ITEM", "EXPIRED_AT_PURCHASE"]
CONDITIONS = ["RESALEABLE", "DAMAGED"]
TRANSFER_STATUS = ["RECEIVED", "LOST_IN_TRANSIT"]
ALERT_TYPES = ["WRONG_STORE", "MISSING_REASON", "COUNT_BEFORE_MOVEMENTS", "TRANSFER_DOUBLE_LOSS",
               "REPEATED_ADJUSTMENTS", "UNEXPLAINED_LOSS"]
CLASSIFICATIONS = ["DATA_ERROR", "PROCESS_ERROR", "SUSPECTED_THEFT"]
SEVERITY = ["LOW", "MEDIUM", "HIGH"]
EVIDENCE_TYPES = ["MOVEMENT", "CYCLE_COUNT", "TRANSFER"]
INV_TYPES = ["LOSS_PREVENTION", "DATA_CORRECTION", "PROCESS_COACHING"]


def col(name, type_, required, desc, allowed=None):
    return dict(name=name, type=type_, required=required, desc=desc, allowed=allowed)


# id: regex every primary-key value must match (single-column keys only)
TABLES = {
    "store": dict(
        desc="A physical store.", pk=["store_id"], id=r"STORE-\d{6}",
        cols=[col("store_id", "TEXT", True, "Primary key."),
              col("store_name", "TEXT", True, "Display name."),
              col("city", "TEXT", True, "City."),
              col("region", "TEXT", True, "Sales region.", REGIONS),
              col("store_format", "TEXT", True, "Store size class; drives traffic.", FORMATS),
              col("sales_area_sqm", "INTEGER", True, "Selling floor area, square metres. > 0."),
              col("opened_date", "DATE", True, "Date the store opened. Before history start.")],
        fks=[]),
    "sku": dict(
        desc="A product (stock keeping unit).", pk=["sku_id"], id=r"SKU-\d{6}",
        cols=[col("sku_id", "TEXT", True, "Primary key."),
              col("sku_name", "TEXT", True, "Brand + variant + item + pack size. Unique."),
              col("category", "TEXT", True, "Product category.", CATEGORIES),
              col("brand", "TEXT", True, "Fictional brand."),
              col("pack_size", "TEXT", True, "Pack size label, e.g. '500 g'."),
              col("unit_cost_inr", "REAL", True, "Cost per unit, INR. > 0."),
              col("unit_price_inr", "REAL", True, "Shelf price per unit, INR. > unit_cost_inr."),
              col("is_perishable", "BOOLEAN", True, "1 if the item can expire.", [0, 1]),
              col("shrink_risk", "TEXT", True, "How attractive the item is to thieves.", RISK)],
        fks=[]),
    "store_sku": dict(
        desc="Bridge: which SKUs each store stocks (many-to-many), with opening and closing book stock.",
        pk=["store_id", "sku_id"],
        cols=[col("store_id", "TEXT", True, "FK -> store."),
              col("sku_id", "TEXT", True, "FK -> sku."),
              col("opening_qty", "INTEGER", True, "Book stock at history start, units. >= 0."),
              col("opening_date", "DATE", True, "Date of the opening balance (history start)."),
              col("closing_book_qty", "INTEGER", True,
                  "opening_qty + sum(all movement quantities), units. >= 0. Calculated, not random.")],
        fks=[(["store_id"], "store", ["store_id"]), (["sku_id"], "sku", ["sku_id"])]),
    "role": dict(
        desc="A job role.", pk=["role_id"], id=r"ROLE-\d{2}",
        cols=[col("role_id", "TEXT", True, "Primary key."),
              col("role_name", "TEXT", True, "Role name.", ROLE_NAMES),
              col("can_post_adjustments", "BOOLEAN", True, "1 if the role may post stock adjustments.", [0, 1])],
        fks=[]),
    "employee": dict(
        desc="A store employee.", pk=["employee_id"], id=r"EMP-\d{6}",
        cols=[col("employee_id", "TEXT", True, "Primary key."),
              col("store_id", "TEXT", True, "FK -> store. Home store."),
              col("first_name", "TEXT", True, "Fictional first name."),
              col("last_name", "TEXT", True, "Fictional last name."),
              col("hire_date", "DATE", True, "Hire date. On or after the store opened.")],
        fks=[(["store_id"], "store", ["store_id"])]),
    "employee_role": dict(
        desc="Bridge: roles an employee holds (many-to-many; supervisors also hold Stock Associate).",
        pk=["employee_id", "role_id"],
        cols=[col("employee_id", "TEXT", True, "FK -> employee."),
              col("role_id", "TEXT", True, "FK -> role."),
              col("effective_from", "DATE", True, "Role start date."),
              col("effective_to", "DATE", False, "Role end date; empty = still active.")],
        fks=[(["employee_id"], "employee", ["employee_id"]), (["role_id"], "role", ["role_id"])]),
    "shift": dict(
        desc="An 8-hour shift at a store. MORNING 06-14, EVENING 14-22, NIGHT 22-06.",
        pk=["shift_id"], id=r"SHF-\d{4}-\d{6}",
        cols=[col("shift_id", "TEXT", True, "Primary key."),
              col("store_id", "TEXT", True, "FK -> store."),
              col("shift_date", "DATE", True, "Business date the shift starts on."),
              col("shift_type", "TEXT", True, "Shift slot.", SHIFT_TYPES),
              col("start_ts", "TIMESTAMP", True, "Shift start."),
              col("end_ts", "TIMESTAMP", True, "Shift end = start + 8 h.")],
        fks=[(["store_id"], "store", ["store_id"])]),
    "shift_assignment": dict(
        desc="Bridge: who worked which shift, in which role (many-to-many).",
        pk=["shift_id", "employee_id"],
        cols=[col("shift_id", "TEXT", True, "FK -> shift."),
              col("employee_id", "TEXT", True, "FK -> employee."),
              col("role_id", "TEXT", True, "FK -> role. Role worked on this shift.")],
        fks=[(["shift_id"], "shift", ["shift_id"]), (["employee_id"], "employee", ["employee_id"]),
             (["role_id"], "role", ["role_id"])]),
    "promotion": dict(
        desc="A price promotion.", pk=["promotion_id"], id=r"PRM-\d{4}-\d{4}",
        cols=[col("promotion_id", "TEXT", True, "Primary key."),
              col("promotion_name", "TEXT", True, "Campaign name."),
              col("start_date", "DATE", True, "First day."),
              col("end_date", "DATE", True, "Last day. >= start_date."),
              col("discount_pct", "INTEGER", True, "Discount off shelf price, percent.", [10, 15, 20, 25, 30])],
        fks=[]),
    "promotion_sku": dict(
        desc="Bridge: SKUs included in a promotion (many-to-many).", pk=["promotion_id", "sku_id"],
        cols=[col("promotion_id", "TEXT", True, "FK -> promotion."),
              col("sku_id", "TEXT", True, "FK -> sku.")],
        fks=[(["promotion_id"], "promotion", ["promotion_id"]), (["sku_id"], "sku", ["sku_id"])]),
    "transfer": dict(
        desc="A stock transfer between two stores. Booked as TRANSFER_OUT + TRANSFER_IN movements.",
        pk=["transfer_id"], id=r"TRF-\d{4}-\d{6}",
        cols=[col("transfer_id", "TEXT", True, "Primary key."),
              col("sku_id", "TEXT", True, "FK -> sku."),
              col("from_store_id", "TEXT", True, "FK -> store. Sending store."),
              col("to_store_id", "TEXT", True, "FK -> store. Receiving store. != from_store_id."),
              col("quantity", "INTEGER", True, "Units shipped. > 0."),
              col("shipped_ts", "TIMESTAMP", True, "When it left the sending store."),
              col("received_ts", "TIMESTAMP", True, "When the receiving store booked it in. > shipped_ts."),
              col("status", "TEXT", True, "LOST_IN_TRANSIT = written off once by the receiving store.",
                  TRANSFER_STATUS)],
        fks=[(["sku_id"], "sku", ["sku_id"]), (["from_store_id"], "store", ["store_id"]),
             (["to_store_id"], "store", ["store_id"])]),
    "inventory_movement": dict(
        desc="Append-only stock ledger. Every stock change is a new row; nothing is ever edited.",
        pk=["movement_id"], id=r"MOV-\d{4}-\d{8}",
        cols=[col("movement_id", "TEXT", True, "Primary key. Assigned in time order."),
              col("movement_ts", "TIMESTAMP", True, "When the movement happened. Inside its shift."),
              col("store_id", "TEXT", True, "FK -> store. Store whose stock changed."),
              col("sku_id", "TEXT", True, "FK -> sku. (store_id, sku_id) FK -> store_sku."),
              col("movement_type", "TEXT", True, "Kind of movement.", MOVEMENT_TYPES),
              col("quantity", "INTEGER", True,
                  "Signed units: + into stock, - out. RECEIPT/TRANSFER_IN/RETURN > 0; SALE/TRANSFER_OUT < 0; "
                  "ADJUSTMENT either sign. Never 0."),
              col("unit_cost_inr", "REAL", True, "SKU cost at the time, INR."),
              col("reason_code", "TEXT", False, "Why stock was adjusted. Required when movement_type = "
                  "ADJUSTMENT, empty otherwise.", REASONS),
              col("note", "TEXT", False, "Free-text note by staff."),
              col("employee_id", "TEXT", True, "FK -> employee who posted it."),
              col("shift_id", "TEXT", True, "FK -> shift it was posted in. Shift store must equal store_id."),
              col("transfer_id", "TEXT", False, "FK -> transfer. Set on TRANSFER_* and TRANSIT_LOSS rows."),
              col("counterparty_store_id", "TEXT", False, "FK -> store. Other store of a transfer."),
              col("promotion_id", "TEXT", False, "FK -> promotion active on a SALE."),
              col("return_id", "TEXT", False, "FK -> customer_return. Set on RETURN and DAMAGED_RETURN rows."),
              col("count_id", "TEXT", False, "FK -> cycle_count. Set on COUNT_VARIANCE rows.")],
        fks=[(["store_id"], "store", ["store_id"]), (["sku_id"], "sku", ["sku_id"]),
             (["store_id", "sku_id"], "store_sku", ["store_id", "sku_id"]),
             (["employee_id"], "employee", ["employee_id"]), (["shift_id"], "shift", ["shift_id"]),
             (["transfer_id"], "transfer", ["transfer_id"]), (["counterparty_store_id"], "store", ["store_id"]),
             (["promotion_id"], "promotion", ["promotion_id"]), (["return_id"], "customer_return", ["return_id"]),
             (["count_id"], "cycle_count", ["count_id"])]),
    "customer_return": dict(
        desc="A customer return. Always linked to the original sale.", pk=["return_id"], id=r"RET-\d{4}-\d{6}",
        cols=[col("return_id", "TEXT", True, "Primary key."),
              col("original_sale_movement_id", "TEXT", True, "FK -> inventory_movement (a SALE)."),
              col("store_id", "TEXT", True, "FK -> store. Same store as the sale."),
              col("sku_id", "TEXT", True, "FK -> sku. Same SKU as the sale."),
              col("quantity", "INTEGER", True, "Units returned. 1 .. units sold."),
              col("return_ts", "TIMESTAMP", True, "When returned. After the sale."),
              col("return_reason", "TEXT", True, "Customer's reason.", RETURN_REASONS),
              col("item_condition", "TEXT", True, "DAMAGED items are written off (DAMAGED_RETURN).", CONDITIONS),
              col("refund_amount_inr", "REAL", True,
                  "quantity x unit_price x (1 - promo discount on the sale), INR. Calculated.")],
        fks=[(["original_sale_movement_id"], "inventory_movement", ["movement_id"]),
             (["store_id"], "store", ["store_id"]), (["sku_id"], "sku", ["sku_id"])]),
    "cycle_count": dict(
        desc="A physical shelf count compared with book stock. Any variance is posted as a new "
             "COUNT_VARIANCE adjustment (history is never overwritten).",
        pk=["count_id"], id=r"CNT-\d{4}-\d{6}",
        cols=[col("count_id", "TEXT", True, "Primary key."),
              col("store_id", "TEXT", True, "FK -> store."),
              col("sku_id", "TEXT", True, "FK -> sku."),
              col("system_qty_as_of_ts", "TIMESTAMP", True,
                  "Moment the book stock (expected_qty) was frozen. Includes every movement up to here."),
              col("count_ts", "TIMESTAMP", True, "When the shelf was counted. Must be >= system_qty_as_of_ts."),
              col("expected_qty", "INTEGER", True,
                  "opening + receipts - sales +/- transfers +/- adjustments + returns up to system_qty_as_of_ts."),
              col("counted_qty", "INTEGER", True, "Units found on the shelf. >= 0."),
              col("variance_qty", "INTEGER", True, "counted_qty - expected_qty. Negative = missing stock."),
              col("variance_value_inr", "REAL", True, "variance_qty x unit_cost, INR."),
              col("employee_id", "TEXT", True, "FK -> employee who counted (a supervisor)."),
              col("shift_id", "TEXT", True, "FK -> shift the count was done in.")],
        fks=[(["store_id"], "store", ["store_id"]), (["sku_id"], "sku", ["sku_id"]),
             (["store_id", "sku_id"], "store_sku", ["store_id", "sku_id"]),
             (["employee_id"], "employee", ["employee_id"]), (["shift_id"], "shift", ["shift_id"])]),
    "shrinkage_alert": dict(
        desc="Detector output: one suspected problem with its evidence and reasons.",
        pk=["alert_id"], id=r"SHR-\d{4}-\d{6}",
        cols=[col("alert_id", "TEXT", True, "Primary key."),
              col("alert_type", "TEXT", True, "Rule that fired.", ALERT_TYPES),
              col("classification", "TEXT", True, "What kind of problem it most likely is.", CLASSIFICATIONS),
              col("store_id", "TEXT", True, "FK -> store."),
              col("sku_id", "TEXT", False, "FK -> sku, when the alert is about one product."),
              col("employee_id", "TEXT", False, "FK -> employee linked to the evidence."),
              col("role_id", "TEXT", False, "FK -> role the employee worked in."),
              col("shift_id", "TEXT", False, "FK -> shift of the key evidence."),
              col("first_evidence_ts", "TIMESTAMP", True, "Earliest evidence."),
              col("last_evidence_ts", "TIMESTAMP", True, "Latest evidence."),
              col("detected_ts", "TIMESTAMP", True, "last_evidence_ts + 1 h."),
              col("loss_units", "INTEGER", True, "Units at stake. >= 0."),
              col("loss_value_inr", "REAL", True, "loss_units x unit_cost, INR."),
              col("risk_score", "REAL", True, "0-100. Base score per rule + value at stake. Calculated."),
              col("severity", "TEXT", True, "HIGH >= 70, MEDIUM >= 40, else LOW.", SEVERITY),
              col("reason_text", "TEXT", True, "Plain-English reasons built only from the evidence numbers.")],
        fks=[(["store_id"], "store", ["store_id"]), (["sku_id"], "sku", ["sku_id"]),
             (["employee_id"], "employee", ["employee_id"]), (["role_id"], "role", ["role_id"]),
             (["shift_id"], "shift", ["shift_id"])]),
    "alert_evidence": dict(
        desc="Bridge: records that back each alert (many-to-many).",
        pk=["alert_id", "evidence_type", "evidence_id"],
        cols=[col("alert_id", "TEXT", True, "FK -> shrinkage_alert."),
              col("evidence_type", "TEXT", True, "Which table evidence_id points to.", EVIDENCE_TYPES),
              col("evidence_id", "TEXT", True, "movement_id, count_id or transfer_id.")],
        fks=[(["alert_id"], "shrinkage_alert", ["alert_id"])]),
    "investigation": dict(
        desc="A case opened for an alert and assigned to the store manager.",
        pk=["investigation_id"], id=r"INV-\d{4}-\d{6}",
        cols=[col("investigation_id", "TEXT", True, "Primary key."),
              col("alert_id", "TEXT", True, "FK -> shrinkage_alert. One case per alert."),
              col("store_id", "TEXT", True, "FK -> store."),
              col("assigned_employee_id", "TEXT", True, "FK -> employee (the store manager)."),
              col("investigation_type", "TEXT", True, "Follows the alert classification.", INV_TYPES),
              col("priority", "TEXT", True, "Same as alert severity.", SEVERITY),
              col("status", "TEXT", True, "All new cases start OPEN.", ["OPEN"]),
              col("opened_ts", "TIMESTAMP", True, "detected_ts + 2 h."),
              col("recommended_action", "TEXT", True, "Next step for the investigator.")],
        fks=[(["alert_id"], "shrinkage_alert", ["alert_id"]), (["store_id"], "store", ["store_id"]),
             (["assigned_employee_id"], "employee", ["employee_id"])]),
}

GROUND_TRUTH = dict(
    desc="Answer key, kept in a separate folder. The detector never reads it.",
    cols=[col("gt_id", "TEXT", True, "Primary key, GT-0001..."),
          col("anomaly_type", "TEXT", True, "What was planted (matches alert_type) or DECOY_DAMAGE_EVENT."),
          col("label", "TEXT", True, "ANOMALY = should be flagged; DECOY = innocent, must not be called theft.",
              ["ANOMALY", "DECOY"]),
          col("entity_type", "TEXT", True, "What a correct alert must point at.",
              ["MOVEMENT", "CYCLE_COUNT", "TRANSFER", "EMPLOYEE", "STORE_DAY"]),
          col("entity_id", "TEXT", True, "The ID a correct alert must point at."),
          col("store_id", "TEXT", True, "Store involved."),
          col("employee_id", "TEXT", False, "Employee involved, if any."),
          col("related_ids", "TEXT", False, "Other rows touched by the planted case, ';'-separated."),
          col("description", "TEXT", True, "What was changed and why it is wrong.")])

SQL_TYPES = {"TEXT": "TEXT", "INTEGER": "INTEGER", "REAL": "REAL", "BOOLEAN": "INTEGER",
             "DATE": "TEXT", "TIMESTAMP": "TEXT"}


def ddl():
    out = []
    for name, t in TABLES.items():
        lines = [f"  {c['name']} {SQL_TYPES[c['type']]}{' NOT NULL' if c['required'] else ''}" for c in t["cols"]]
        lines.append(f"  PRIMARY KEY ({', '.join(t['pk'])})")
        lines += [f"  FOREIGN KEY ({', '.join(a)}) REFERENCES {rt} ({', '.join(b)})" for a, rt, b in t["fks"]]
        out.append(f"CREATE TABLE {name} (\n" + ",\n".join(lines) + "\n);")
    return "\n\n".join(out) + "\n"


PG_TYPES = {"TEXT": "TEXT", "INTEGER": "INTEGER", "REAL": "DOUBLE PRECISION", "BOOLEAN": "SMALLINT",
            "DATE": "DATE", "TIMESTAMP": "TIMESTAMP"}
PG_TABLES = {**TABLES, "ground_truth": {**GROUND_TRUTH, "pk": ["gt_id"], "fks": []}}


def pg_ddl():
    """Postgres DDL as (create_tables, add_foreign_keys). Keys are added after the bulk load because the
    ledger and customer returns reference each other; adding them then also validates every row."""
    tables, fks = [], []
    for name, t in PG_TABLES.items():
        lines = [f"  {c['name']} {PG_TYPES[c['type']]}{' NOT NULL' if c['required'] else ''}" for c in t["cols"]]
        lines.append(f"  PRIMARY KEY ({', '.join(t['pk'])})")
        tables.append(f"CREATE TABLE {name} (\n" + ",\n".join(lines) + "\n);")
        fks += [f"ALTER TABLE {name} ADD CONSTRAINT fk_{name}_{'_'.join(a)} FOREIGN KEY ({', '.join(a)}) "
                f"REFERENCES {rt} ({', '.join(b)});" for a, rt, b in t["fks"]]
    tables.append("CREATE TABLE pipeline_report (\n  name TEXT PRIMARY KEY,\n  body JSONB NOT NULL\n);")
    indexes = ["CREATE INDEX ix_alert_type ON shrinkage_alert (alert_type);",
               "CREATE INDEX ix_alert_class ON shrinkage_alert (classification, severity);",
               "CREATE INDEX ix_alert_store ON shrinkage_alert (store_id);",
               "CREATE INDEX ix_movement_store_sku_ts ON inventory_movement (store_id, sku_id, movement_ts);"]
    return "\n\n".join(tables) + "\n", "\n".join(fks + indexes) + "\n"


def dictionary_md():
    def table_md(name, t):
        md = [f"## {name}\n", t["desc"] + "\n"]
        if "pk" in t:
            md.append(f"**Primary key:** `{', '.join(t['pk'])}`" + (f" — format `{t['id']}`" if t.get("id") else ""))
            for a, rt, b in t["fks"]:
                md.append(f"<br>**FK:** `{', '.join(a)}` → `{rt}({', '.join(b)})`")
            md.append("\n")
        md.append("| Field | Type | Required | Allowed values | Meaning / units / rule |")
        md.append("|---|---|---|---|---|")
        for c in t["cols"]:
            allowed = ", ".join(map(str, c["allowed"])) if c["allowed"] else ""
            md.append(f"| `{c['name']}` | {c['type']} | {'yes' if c['required'] else 'no'} | {allowed} | {c['desc']} |")
        return "\n".join(md) + "\n"

    head = ("# Data dictionary\n\nGenerated from `schema.py` (`python -m app.pipeline.schema`, run from backend/). Dates are `YYYY-MM-DD`, "
            "timestamps `YYYY-MM-DD HH:MM:SS` (store local time), money in INR, quantities in units.\n\n")
    body = "\n".join(table_md(n, t) for n, t in TABLES.items())
    return head + body + "\n" + table_md("ground_truth/anomalies (answer key)", GROUND_TRUTH)


if __name__ == "__main__":
    here = Path(__file__).resolve().parents[3] / "docs"
    (here / "schema.sql").write_text(ddl(), encoding="utf-8", newline="\n")
    create, keys = pg_ddl()
    (here / "schema.postgres.sql").write_text("-- Postgres / Supabase. Tables, then keys + indexes (added after load).\n\n"
                                              + create + "\n" + keys, encoding="utf-8", newline="\n")
    (here / "data_dictionary.md").write_text(dictionary_md(), encoding="utf-8", newline="\n")
    print("wrote schema.sql and data_dictionary.md")
