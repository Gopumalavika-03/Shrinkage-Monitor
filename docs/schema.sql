CREATE TABLE store (
  store_id TEXT NOT NULL,
  store_name TEXT NOT NULL,
  city TEXT NOT NULL,
  region TEXT NOT NULL,
  store_format TEXT NOT NULL,
  sales_area_sqm INTEGER NOT NULL,
  opened_date TEXT NOT NULL,
  PRIMARY KEY (store_id)
);

CREATE TABLE sku (
  sku_id TEXT NOT NULL,
  sku_name TEXT NOT NULL,
  category TEXT NOT NULL,
  brand TEXT NOT NULL,
  pack_size TEXT NOT NULL,
  unit_cost_inr REAL NOT NULL,
  unit_price_inr REAL NOT NULL,
  is_perishable INTEGER NOT NULL,
  shrink_risk TEXT NOT NULL,
  PRIMARY KEY (sku_id)
);

CREATE TABLE store_sku (
  store_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  opening_qty INTEGER NOT NULL,
  opening_date TEXT NOT NULL,
  closing_book_qty INTEGER NOT NULL,
  PRIMARY KEY (store_id, sku_id),
  FOREIGN KEY (store_id) REFERENCES store (store_id),
  FOREIGN KEY (sku_id) REFERENCES sku (sku_id)
);

CREATE TABLE role (
  role_id TEXT NOT NULL,
  role_name TEXT NOT NULL,
  can_post_adjustments INTEGER NOT NULL,
  PRIMARY KEY (role_id)
);

CREATE TABLE employee (
  employee_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  hire_date TEXT NOT NULL,
  PRIMARY KEY (employee_id),
  FOREIGN KEY (store_id) REFERENCES store (store_id)
);

CREATE TABLE employee_role (
  employee_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  PRIMARY KEY (employee_id, role_id),
  FOREIGN KEY (employee_id) REFERENCES employee (employee_id),
  FOREIGN KEY (role_id) REFERENCES role (role_id)
);

CREATE TABLE shift (
  shift_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  shift_date TEXT NOT NULL,
  shift_type TEXT NOT NULL,
  start_ts TEXT NOT NULL,
  end_ts TEXT NOT NULL,
  PRIMARY KEY (shift_id),
  FOREIGN KEY (store_id) REFERENCES store (store_id)
);

CREATE TABLE shift_assignment (
  shift_id TEXT NOT NULL,
  employee_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  PRIMARY KEY (shift_id, employee_id),
  FOREIGN KEY (shift_id) REFERENCES shift (shift_id),
  FOREIGN KEY (employee_id) REFERENCES employee (employee_id),
  FOREIGN KEY (role_id) REFERENCES role (role_id)
);

CREATE TABLE promotion (
  promotion_id TEXT NOT NULL,
  promotion_name TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  discount_pct INTEGER NOT NULL,
  PRIMARY KEY (promotion_id)
);

CREATE TABLE promotion_sku (
  promotion_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  PRIMARY KEY (promotion_id, sku_id),
  FOREIGN KEY (promotion_id) REFERENCES promotion (promotion_id),
  FOREIGN KEY (sku_id) REFERENCES sku (sku_id)
);

CREATE TABLE transfer (
  transfer_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  from_store_id TEXT NOT NULL,
  to_store_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  shipped_ts TEXT NOT NULL,
  received_ts TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (transfer_id),
  FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
  FOREIGN KEY (from_store_id) REFERENCES store (store_id),
  FOREIGN KEY (to_store_id) REFERENCES store (store_id)
);

CREATE TABLE inventory_movement (
  movement_id TEXT NOT NULL,
  movement_ts TEXT NOT NULL,
  store_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  movement_type TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit_cost_inr REAL NOT NULL,
  reason_code TEXT,
  note TEXT,
  employee_id TEXT NOT NULL,
  shift_id TEXT NOT NULL,
  transfer_id TEXT,
  counterparty_store_id TEXT,
  promotion_id TEXT,
  return_id TEXT,
  count_id TEXT,
  PRIMARY KEY (movement_id),
  FOREIGN KEY (store_id) REFERENCES store (store_id),
  FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
  FOREIGN KEY (store_id, sku_id) REFERENCES store_sku (store_id, sku_id),
  FOREIGN KEY (employee_id) REFERENCES employee (employee_id),
  FOREIGN KEY (shift_id) REFERENCES shift (shift_id),
  FOREIGN KEY (transfer_id) REFERENCES transfer (transfer_id),
  FOREIGN KEY (counterparty_store_id) REFERENCES store (store_id),
  FOREIGN KEY (promotion_id) REFERENCES promotion (promotion_id),
  FOREIGN KEY (return_id) REFERENCES customer_return (return_id),
  FOREIGN KEY (count_id) REFERENCES cycle_count (count_id)
);

CREATE TABLE customer_return (
  return_id TEXT NOT NULL,
  original_sale_movement_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  return_ts TEXT NOT NULL,
  return_reason TEXT NOT NULL,
  item_condition TEXT NOT NULL,
  refund_amount_inr REAL NOT NULL,
  PRIMARY KEY (return_id),
  FOREIGN KEY (original_sale_movement_id) REFERENCES inventory_movement (movement_id),
  FOREIGN KEY (store_id) REFERENCES store (store_id),
  FOREIGN KEY (sku_id) REFERENCES sku (sku_id)
);

CREATE TABLE cycle_count (
  count_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  system_qty_as_of_ts TEXT NOT NULL,
  count_ts TEXT NOT NULL,
  expected_qty INTEGER NOT NULL,
  counted_qty INTEGER NOT NULL,
  variance_qty INTEGER NOT NULL,
  variance_value_inr REAL NOT NULL,
  employee_id TEXT NOT NULL,
  shift_id TEXT NOT NULL,
  PRIMARY KEY (count_id),
  FOREIGN KEY (store_id) REFERENCES store (store_id),
  FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
  FOREIGN KEY (store_id, sku_id) REFERENCES store_sku (store_id, sku_id),
  FOREIGN KEY (employee_id) REFERENCES employee (employee_id),
  FOREIGN KEY (shift_id) REFERENCES shift (shift_id)
);

CREATE TABLE shrinkage_alert (
  alert_id TEXT NOT NULL,
  alert_type TEXT NOT NULL,
  classification TEXT NOT NULL,
  store_id TEXT NOT NULL,
  sku_id TEXT,
  employee_id TEXT,
  role_id TEXT,
  shift_id TEXT,
  first_evidence_ts TEXT NOT NULL,
  last_evidence_ts TEXT NOT NULL,
  detected_ts TEXT NOT NULL,
  loss_units INTEGER NOT NULL,
  loss_value_inr REAL NOT NULL,
  risk_score REAL NOT NULL,
  severity TEXT NOT NULL,
  reason_text TEXT NOT NULL,
  PRIMARY KEY (alert_id),
  FOREIGN KEY (store_id) REFERENCES store (store_id),
  FOREIGN KEY (sku_id) REFERENCES sku (sku_id),
  FOREIGN KEY (employee_id) REFERENCES employee (employee_id),
  FOREIGN KEY (role_id) REFERENCES role (role_id),
  FOREIGN KEY (shift_id) REFERENCES shift (shift_id)
);

CREATE TABLE alert_evidence (
  alert_id TEXT NOT NULL,
  evidence_type TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  PRIMARY KEY (alert_id, evidence_type, evidence_id),
  FOREIGN KEY (alert_id) REFERENCES shrinkage_alert (alert_id)
);

CREATE TABLE investigation (
  investigation_id TEXT NOT NULL,
  alert_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  assigned_employee_id TEXT NOT NULL,
  investigation_type TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  opened_ts TEXT NOT NULL,
  recommended_action TEXT NOT NULL,
  PRIMARY KEY (investigation_id),
  FOREIGN KEY (alert_id) REFERENCES shrinkage_alert (alert_id),
  FOREIGN KEY (store_id) REFERENCES store (store_id),
  FOREIGN KEY (assigned_employee_id) REFERENCES employee (employee_id)
);
