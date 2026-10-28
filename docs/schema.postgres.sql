-- Postgres / Supabase. Tables, then keys + indexes (added after load).

CREATE TABLE store (
  store_id TEXT NOT NULL,
  store_name TEXT NOT NULL,
  city TEXT NOT NULL,
  region TEXT NOT NULL,
  store_format TEXT NOT NULL,
  sales_area_sqm INTEGER NOT NULL,
  opened_date DATE NOT NULL,
  PRIMARY KEY (store_id)
);

CREATE TABLE sku (
  sku_id TEXT NOT NULL,
  sku_name TEXT NOT NULL,
  category TEXT NOT NULL,
  brand TEXT NOT NULL,
  pack_size TEXT NOT NULL,
  unit_cost_inr DOUBLE PRECISION NOT NULL,
  unit_price_inr DOUBLE PRECISION NOT NULL,
  is_perishable SMALLINT NOT NULL,
  shrink_risk TEXT NOT NULL,
  PRIMARY KEY (sku_id)
);

CREATE TABLE store_sku (
  store_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  opening_qty INTEGER NOT NULL,
  opening_date DATE NOT NULL,
  closing_book_qty INTEGER NOT NULL,
  PRIMARY KEY (store_id, sku_id)
);

CREATE TABLE role (
  role_id TEXT NOT NULL,
  role_name TEXT NOT NULL,
  can_post_adjustments SMALLINT NOT NULL,
  PRIMARY KEY (role_id)
);

CREATE TABLE employee (
  employee_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  hire_date DATE NOT NULL,
  PRIMARY KEY (employee_id)
);

CREATE TABLE employee_role (
  employee_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE,
  PRIMARY KEY (employee_id, role_id)
);

CREATE TABLE shift (
  shift_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  shift_date DATE NOT NULL,
  shift_type TEXT NOT NULL,
  start_ts TIMESTAMP NOT NULL,
  end_ts TIMESTAMP NOT NULL,
  PRIMARY KEY (shift_id)
);

CREATE TABLE shift_assignment (
  shift_id TEXT NOT NULL,
  employee_id TEXT NOT NULL,
  role_id TEXT NOT NULL,
  PRIMARY KEY (shift_id, employee_id)
);

CREATE TABLE promotion (
  promotion_id TEXT NOT NULL,
  promotion_name TEXT NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  discount_pct INTEGER NOT NULL,
  PRIMARY KEY (promotion_id)
);

CREATE TABLE promotion_sku (
  promotion_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  PRIMARY KEY (promotion_id, sku_id)
);

CREATE TABLE transfer (
  transfer_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  from_store_id TEXT NOT NULL,
  to_store_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  shipped_ts TIMESTAMP NOT NULL,
  received_ts TIMESTAMP NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (transfer_id)
);

CREATE TABLE inventory_movement (
  movement_id TEXT NOT NULL,
  movement_ts TIMESTAMP NOT NULL,
  store_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  movement_type TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit_cost_inr DOUBLE PRECISION NOT NULL,
  reason_code TEXT,
  note TEXT,
  employee_id TEXT NOT NULL,
  shift_id TEXT NOT NULL,
  transfer_id TEXT,
  counterparty_store_id TEXT,
  promotion_id TEXT,
  return_id TEXT,
  count_id TEXT,
  PRIMARY KEY (movement_id)
);

CREATE TABLE customer_return (
  return_id TEXT NOT NULL,
  original_sale_movement_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  return_ts TIMESTAMP NOT NULL,
  return_reason TEXT NOT NULL,
  item_condition TEXT NOT NULL,
  refund_amount_inr DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (return_id)
);

CREATE TABLE cycle_count (
  count_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  sku_id TEXT NOT NULL,
  system_qty_as_of_ts TIMESTAMP NOT NULL,
  count_ts TIMESTAMP NOT NULL,
  expected_qty INTEGER NOT NULL,
  counted_qty INTEGER NOT NULL,
  variance_qty INTEGER NOT NULL,
  variance_value_inr DOUBLE PRECISION NOT NULL,
  employee_id TEXT NOT NULL,
  shift_id TEXT NOT NULL,
  PRIMARY KEY (count_id)
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
  first_evidence_ts TIMESTAMP NOT NULL,
  last_evidence_ts TIMESTAMP NOT NULL,
  detected_ts TIMESTAMP NOT NULL,
  loss_units INTEGER NOT NULL,
  loss_value_inr DOUBLE PRECISION NOT NULL,
  risk_score DOUBLE PRECISION NOT NULL,
  severity TEXT NOT NULL,
  reason_text TEXT NOT NULL,
  PRIMARY KEY (alert_id)
);

CREATE TABLE alert_evidence (
  alert_id TEXT NOT NULL,
  evidence_type TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  PRIMARY KEY (alert_id, evidence_type, evidence_id)
);

CREATE TABLE investigation (
  investigation_id TEXT NOT NULL,
  alert_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  assigned_employee_id TEXT NOT NULL,
  investigation_type TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  opened_ts TIMESTAMP NOT NULL,
  recommended_action TEXT NOT NULL,
  PRIMARY KEY (investigation_id)
);

CREATE TABLE ground_truth (
  gt_id TEXT NOT NULL,
  anomaly_type TEXT NOT NULL,
  label TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  store_id TEXT NOT NULL,
  employee_id TEXT,
  related_ids TEXT,
  description TEXT NOT NULL,
  PRIMARY KEY (gt_id)
);

CREATE TABLE pipeline_report (
  name TEXT PRIMARY KEY,
  body JSONB NOT NULL
);

ALTER TABLE store_sku ADD CONSTRAINT fk_store_sku_store_id FOREIGN KEY (store_id) REFERENCES store (store_id);
ALTER TABLE store_sku ADD CONSTRAINT fk_store_sku_sku_id FOREIGN KEY (sku_id) REFERENCES sku (sku_id);
ALTER TABLE employee ADD CONSTRAINT fk_employee_store_id FOREIGN KEY (store_id) REFERENCES store (store_id);
ALTER TABLE employee_role ADD CONSTRAINT fk_employee_role_employee_id FOREIGN KEY (employee_id) REFERENCES employee (employee_id);
ALTER TABLE employee_role ADD CONSTRAINT fk_employee_role_role_id FOREIGN KEY (role_id) REFERENCES role (role_id);
ALTER TABLE shift ADD CONSTRAINT fk_shift_store_id FOREIGN KEY (store_id) REFERENCES store (store_id);
ALTER TABLE shift_assignment ADD CONSTRAINT fk_shift_assignment_shift_id FOREIGN KEY (shift_id) REFERENCES shift (shift_id);
ALTER TABLE shift_assignment ADD CONSTRAINT fk_shift_assignment_employee_id FOREIGN KEY (employee_id) REFERENCES employee (employee_id);
ALTER TABLE shift_assignment ADD CONSTRAINT fk_shift_assignment_role_id FOREIGN KEY (role_id) REFERENCES role (role_id);
ALTER TABLE promotion_sku ADD CONSTRAINT fk_promotion_sku_promotion_id FOREIGN KEY (promotion_id) REFERENCES promotion (promotion_id);
ALTER TABLE promotion_sku ADD CONSTRAINT fk_promotion_sku_sku_id FOREIGN KEY (sku_id) REFERENCES sku (sku_id);
ALTER TABLE transfer ADD CONSTRAINT fk_transfer_sku_id FOREIGN KEY (sku_id) REFERENCES sku (sku_id);
ALTER TABLE transfer ADD CONSTRAINT fk_transfer_from_store_id FOREIGN KEY (from_store_id) REFERENCES store (store_id);
ALTER TABLE transfer ADD CONSTRAINT fk_transfer_to_store_id FOREIGN KEY (to_store_id) REFERENCES store (store_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_store_id FOREIGN KEY (store_id) REFERENCES store (store_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_sku_id FOREIGN KEY (sku_id) REFERENCES sku (sku_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_store_id_sku_id FOREIGN KEY (store_id, sku_id) REFERENCES store_sku (store_id, sku_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_employee_id FOREIGN KEY (employee_id) REFERENCES employee (employee_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_shift_id FOREIGN KEY (shift_id) REFERENCES shift (shift_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_transfer_id FOREIGN KEY (transfer_id) REFERENCES transfer (transfer_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_counterparty_store_id FOREIGN KEY (counterparty_store_id) REFERENCES store (store_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_promotion_id FOREIGN KEY (promotion_id) REFERENCES promotion (promotion_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_return_id FOREIGN KEY (return_id) REFERENCES customer_return (return_id);
ALTER TABLE inventory_movement ADD CONSTRAINT fk_inventory_movement_count_id FOREIGN KEY (count_id) REFERENCES cycle_count (count_id);
ALTER TABLE customer_return ADD CONSTRAINT fk_customer_return_original_sale_movement_id FOREIGN KEY (original_sale_movement_id) REFERENCES inventory_movement (movement_id);
ALTER TABLE customer_return ADD CONSTRAINT fk_customer_return_store_id FOREIGN KEY (store_id) REFERENCES store (store_id);
ALTER TABLE customer_return ADD CONSTRAINT fk_customer_return_sku_id FOREIGN KEY (sku_id) REFERENCES sku (sku_id);
ALTER TABLE cycle_count ADD CONSTRAINT fk_cycle_count_store_id FOREIGN KEY (store_id) REFERENCES store (store_id);
ALTER TABLE cycle_count ADD CONSTRAINT fk_cycle_count_sku_id FOREIGN KEY (sku_id) REFERENCES sku (sku_id);
ALTER TABLE cycle_count ADD CONSTRAINT fk_cycle_count_store_id_sku_id FOREIGN KEY (store_id, sku_id) REFERENCES store_sku (store_id, sku_id);
ALTER TABLE cycle_count ADD CONSTRAINT fk_cycle_count_employee_id FOREIGN KEY (employee_id) REFERENCES employee (employee_id);
ALTER TABLE cycle_count ADD CONSTRAINT fk_cycle_count_shift_id FOREIGN KEY (shift_id) REFERENCES shift (shift_id);
ALTER TABLE shrinkage_alert ADD CONSTRAINT fk_shrinkage_alert_store_id FOREIGN KEY (store_id) REFERENCES store (store_id);
ALTER TABLE shrinkage_alert ADD CONSTRAINT fk_shrinkage_alert_sku_id FOREIGN KEY (sku_id) REFERENCES sku (sku_id);
ALTER TABLE shrinkage_alert ADD CONSTRAINT fk_shrinkage_alert_employee_id FOREIGN KEY (employee_id) REFERENCES employee (employee_id);
ALTER TABLE shrinkage_alert ADD CONSTRAINT fk_shrinkage_alert_role_id FOREIGN KEY (role_id) REFERENCES role (role_id);
ALTER TABLE shrinkage_alert ADD CONSTRAINT fk_shrinkage_alert_shift_id FOREIGN KEY (shift_id) REFERENCES shift (shift_id);
ALTER TABLE alert_evidence ADD CONSTRAINT fk_alert_evidence_alert_id FOREIGN KEY (alert_id) REFERENCES shrinkage_alert (alert_id);
ALTER TABLE investigation ADD CONSTRAINT fk_investigation_alert_id FOREIGN KEY (alert_id) REFERENCES shrinkage_alert (alert_id);
ALTER TABLE investigation ADD CONSTRAINT fk_investigation_store_id FOREIGN KEY (store_id) REFERENCES store (store_id);
ALTER TABLE investigation ADD CONSTRAINT fk_investigation_assigned_employee_id FOREIGN KEY (assigned_employee_id) REFERENCES employee (employee_id);
CREATE INDEX ix_alert_type ON shrinkage_alert (alert_type);
CREATE INDEX ix_alert_class ON shrinkage_alert (classification, severity);
CREATE INDEX ix_alert_store ON shrinkage_alert (store_id);
CREATE INDEX ix_movement_store_sku_ts ON inventory_movement (store_id, sku_id, movement_ts);
