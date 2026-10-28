# Data dictionary

Generated from `schema.py` (`python -m app.pipeline.schema`, run from backend/). Dates are `YYYY-MM-DD`, timestamps `YYYY-MM-DD HH:MM:SS` (store local time), money in INR, quantities in units.

## store

A physical store.

**Primary key:** `store_id` — format `STORE-\d{6}`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `store_id` | TEXT | yes |  | Primary key. |
| `store_name` | TEXT | yes |  | Display name. |
| `city` | TEXT | yes |  | City. |
| `region` | TEXT | yes | North, South, East, West, Central | Sales region. |
| `store_format` | TEXT | yes | HYPERMARKET, SUPERMARKET, EXPRESS | Store size class; drives traffic. |
| `sales_area_sqm` | INTEGER | yes |  | Selling floor area, square metres. > 0. |
| `opened_date` | DATE | yes |  | Date the store opened. Before history start. |

## sku

A product (stock keeping unit).

**Primary key:** `sku_id` — format `SKU-\d{6}`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `sku_id` | TEXT | yes |  | Primary key. |
| `sku_name` | TEXT | yes |  | Brand + variant + item + pack size. Unique. |
| `category` | TEXT | yes | Fresh Produce, Dairy, Bakery, Beverages, Snacks, Household, Personal Care, Electronics Accessories, Apparel Basics, Health & Pharmacy | Product category. |
| `brand` | TEXT | yes |  | Fictional brand. |
| `pack_size` | TEXT | yes |  | Pack size label, e.g. '500 g'. |
| `unit_cost_inr` | REAL | yes |  | Cost per unit, INR. > 0. |
| `unit_price_inr` | REAL | yes |  | Shelf price per unit, INR. > unit_cost_inr. |
| `is_perishable` | BOOLEAN | yes | 0, 1 | 1 if the item can expire. |
| `shrink_risk` | TEXT | yes | LOW, MEDIUM, HIGH | How attractive the item is to thieves. |

## store_sku

Bridge: which SKUs each store stocks (many-to-many), with opening and closing book stock.

**Primary key:** `store_id, sku_id`
<br>**FK:** `store_id` → `store(store_id)`
<br>**FK:** `sku_id` → `sku(sku_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `store_id` | TEXT | yes |  | FK -> store. |
| `sku_id` | TEXT | yes |  | FK -> sku. |
| `opening_qty` | INTEGER | yes |  | Book stock at history start, units. >= 0. |
| `opening_date` | DATE | yes |  | Date of the opening balance (history start). |
| `closing_book_qty` | INTEGER | yes |  | opening_qty + sum(all movement quantities), units. >= 0. Calculated, not random. |

## role

A job role.

**Primary key:** `role_id` — format `ROLE-\d{2}`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `role_id` | TEXT | yes |  | Primary key. |
| `role_name` | TEXT | yes | Cashier, Stock Associate, Shift Supervisor, Store Manager | Role name. |
| `can_post_adjustments` | BOOLEAN | yes | 0, 1 | 1 if the role may post stock adjustments. |

## employee

A store employee.

**Primary key:** `employee_id` — format `EMP-\d{6}`
<br>**FK:** `store_id` → `store(store_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `employee_id` | TEXT | yes |  | Primary key. |
| `store_id` | TEXT | yes |  | FK -> store. Home store. |
| `first_name` | TEXT | yes |  | Fictional first name. |
| `last_name` | TEXT | yes |  | Fictional last name. |
| `hire_date` | DATE | yes |  | Hire date. On or after the store opened. |

## employee_role

Bridge: roles an employee holds (many-to-many; supervisors also hold Stock Associate).

**Primary key:** `employee_id, role_id`
<br>**FK:** `employee_id` → `employee(employee_id)`
<br>**FK:** `role_id` → `role(role_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `employee_id` | TEXT | yes |  | FK -> employee. |
| `role_id` | TEXT | yes |  | FK -> role. |
| `effective_from` | DATE | yes |  | Role start date. |
| `effective_to` | DATE | no |  | Role end date; empty = still active. |

## shift

An 8-hour shift at a store. MORNING 06-14, EVENING 14-22, NIGHT 22-06.

**Primary key:** `shift_id` — format `SHF-\d{4}-\d{6}`
<br>**FK:** `store_id` → `store(store_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `shift_id` | TEXT | yes |  | Primary key. |
| `store_id` | TEXT | yes |  | FK -> store. |
| `shift_date` | DATE | yes |  | Business date the shift starts on. |
| `shift_type` | TEXT | yes | MORNING, EVENING, NIGHT | Shift slot. |
| `start_ts` | TIMESTAMP | yes |  | Shift start. |
| `end_ts` | TIMESTAMP | yes |  | Shift end = start + 8 h. |

## shift_assignment

Bridge: who worked which shift, in which role (many-to-many).

**Primary key:** `shift_id, employee_id`
<br>**FK:** `shift_id` → `shift(shift_id)`
<br>**FK:** `employee_id` → `employee(employee_id)`
<br>**FK:** `role_id` → `role(role_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `shift_id` | TEXT | yes |  | FK -> shift. |
| `employee_id` | TEXT | yes |  | FK -> employee. |
| `role_id` | TEXT | yes |  | FK -> role. Role worked on this shift. |

## promotion

A price promotion.

**Primary key:** `promotion_id` — format `PRM-\d{4}-\d{4}`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `promotion_id` | TEXT | yes |  | Primary key. |
| `promotion_name` | TEXT | yes |  | Campaign name. |
| `start_date` | DATE | yes |  | First day. |
| `end_date` | DATE | yes |  | Last day. >= start_date. |
| `discount_pct` | INTEGER | yes | 10, 15, 20, 25, 30 | Discount off shelf price, percent. |

## promotion_sku

Bridge: SKUs included in a promotion (many-to-many).

**Primary key:** `promotion_id, sku_id`
<br>**FK:** `promotion_id` → `promotion(promotion_id)`
<br>**FK:** `sku_id` → `sku(sku_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `promotion_id` | TEXT | yes |  | FK -> promotion. |
| `sku_id` | TEXT | yes |  | FK -> sku. |

## transfer

A stock transfer between two stores. Booked as TRANSFER_OUT + TRANSFER_IN movements.

**Primary key:** `transfer_id` — format `TRF-\d{4}-\d{6}`
<br>**FK:** `sku_id` → `sku(sku_id)`
<br>**FK:** `from_store_id` → `store(store_id)`
<br>**FK:** `to_store_id` → `store(store_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `transfer_id` | TEXT | yes |  | Primary key. |
| `sku_id` | TEXT | yes |  | FK -> sku. |
| `from_store_id` | TEXT | yes |  | FK -> store. Sending store. |
| `to_store_id` | TEXT | yes |  | FK -> store. Receiving store. != from_store_id. |
| `quantity` | INTEGER | yes |  | Units shipped. > 0. |
| `shipped_ts` | TIMESTAMP | yes |  | When it left the sending store. |
| `received_ts` | TIMESTAMP | yes |  | When the receiving store booked it in. > shipped_ts. |
| `status` | TEXT | yes | RECEIVED, LOST_IN_TRANSIT | LOST_IN_TRANSIT = written off once by the receiving store. |

## inventory_movement

Append-only stock ledger. Every stock change is a new row; nothing is ever edited.

**Primary key:** `movement_id` — format `MOV-\d{4}-\d{8}`
<br>**FK:** `store_id` → `store(store_id)`
<br>**FK:** `sku_id` → `sku(sku_id)`
<br>**FK:** `store_id, sku_id` → `store_sku(store_id, sku_id)`
<br>**FK:** `employee_id` → `employee(employee_id)`
<br>**FK:** `shift_id` → `shift(shift_id)`
<br>**FK:** `transfer_id` → `transfer(transfer_id)`
<br>**FK:** `counterparty_store_id` → `store(store_id)`
<br>**FK:** `promotion_id` → `promotion(promotion_id)`
<br>**FK:** `return_id` → `customer_return(return_id)`
<br>**FK:** `count_id` → `cycle_count(count_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `movement_id` | TEXT | yes |  | Primary key. Assigned in time order. |
| `movement_ts` | TIMESTAMP | yes |  | When the movement happened. Inside its shift. |
| `store_id` | TEXT | yes |  | FK -> store. Store whose stock changed. |
| `sku_id` | TEXT | yes |  | FK -> sku. (store_id, sku_id) FK -> store_sku. |
| `movement_type` | TEXT | yes | RECEIPT, SALE, TRANSFER_OUT, TRANSFER_IN, ADJUSTMENT, RETURN | Kind of movement. |
| `quantity` | INTEGER | yes |  | Signed units: + into stock, - out. RECEIPT/TRANSFER_IN/RETURN > 0; SALE/TRANSFER_OUT < 0; ADJUSTMENT either sign. Never 0. |
| `unit_cost_inr` | REAL | yes |  | SKU cost at the time, INR. |
| `reason_code` | TEXT | no | DAMAGE, EXPIRED, MISCOUNT, FOUND, DAMAGED_RETURN, TRANSIT_LOSS, COUNT_VARIANCE | Why stock was adjusted. Required when movement_type = ADJUSTMENT, empty otherwise. |
| `note` | TEXT | no |  | Free-text note by staff. |
| `employee_id` | TEXT | yes |  | FK -> employee who posted it. |
| `shift_id` | TEXT | yes |  | FK -> shift it was posted in. Shift store must equal store_id. |
| `transfer_id` | TEXT | no |  | FK -> transfer. Set on TRANSFER_* and TRANSIT_LOSS rows. |
| `counterparty_store_id` | TEXT | no |  | FK -> store. Other store of a transfer. |
| `promotion_id` | TEXT | no |  | FK -> promotion active on a SALE. |
| `return_id` | TEXT | no |  | FK -> customer_return. Set on RETURN and DAMAGED_RETURN rows. |
| `count_id` | TEXT | no |  | FK -> cycle_count. Set on COUNT_VARIANCE rows. |

## customer_return

A customer return. Always linked to the original sale.

**Primary key:** `return_id` — format `RET-\d{4}-\d{6}`
<br>**FK:** `original_sale_movement_id` → `inventory_movement(movement_id)`
<br>**FK:** `store_id` → `store(store_id)`
<br>**FK:** `sku_id` → `sku(sku_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `return_id` | TEXT | yes |  | Primary key. |
| `original_sale_movement_id` | TEXT | yes |  | FK -> inventory_movement (a SALE). |
| `store_id` | TEXT | yes |  | FK -> store. Same store as the sale. |
| `sku_id` | TEXT | yes |  | FK -> sku. Same SKU as the sale. |
| `quantity` | INTEGER | yes |  | Units returned. 1 .. units sold. |
| `return_ts` | TIMESTAMP | yes |  | When returned. After the sale. |
| `return_reason` | TEXT | yes | DEFECTIVE, CHANGED_MIND, WRONG_ITEM, EXPIRED_AT_PURCHASE | Customer's reason. |
| `item_condition` | TEXT | yes | RESALEABLE, DAMAGED | DAMAGED items are written off (DAMAGED_RETURN). |
| `refund_amount_inr` | REAL | yes |  | quantity x unit_price x (1 - promo discount on the sale), INR. Calculated. |

## cycle_count

A physical shelf count compared with book stock. Any variance is posted as a new COUNT_VARIANCE adjustment (history is never overwritten).

**Primary key:** `count_id` — format `CNT-\d{4}-\d{6}`
<br>**FK:** `store_id` → `store(store_id)`
<br>**FK:** `sku_id` → `sku(sku_id)`
<br>**FK:** `store_id, sku_id` → `store_sku(store_id, sku_id)`
<br>**FK:** `employee_id` → `employee(employee_id)`
<br>**FK:** `shift_id` → `shift(shift_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `count_id` | TEXT | yes |  | Primary key. |
| `store_id` | TEXT | yes |  | FK -> store. |
| `sku_id` | TEXT | yes |  | FK -> sku. |
| `system_qty_as_of_ts` | TIMESTAMP | yes |  | Moment the book stock (expected_qty) was frozen. Includes every movement up to here. |
| `count_ts` | TIMESTAMP | yes |  | When the shelf was counted. Must be >= system_qty_as_of_ts. |
| `expected_qty` | INTEGER | yes |  | opening + receipts - sales +/- transfers +/- adjustments + returns up to system_qty_as_of_ts. |
| `counted_qty` | INTEGER | yes |  | Units found on the shelf. >= 0. |
| `variance_qty` | INTEGER | yes |  | counted_qty - expected_qty. Negative = missing stock. |
| `variance_value_inr` | REAL | yes |  | variance_qty x unit_cost, INR. |
| `employee_id` | TEXT | yes |  | FK -> employee who counted (a supervisor). |
| `shift_id` | TEXT | yes |  | FK -> shift the count was done in. |

## shrinkage_alert

Detector output: one suspected problem with its evidence and reasons.

**Primary key:** `alert_id` — format `SHR-\d{4}-\d{6}`
<br>**FK:** `store_id` → `store(store_id)`
<br>**FK:** `sku_id` → `sku(sku_id)`
<br>**FK:** `employee_id` → `employee(employee_id)`
<br>**FK:** `role_id` → `role(role_id)`
<br>**FK:** `shift_id` → `shift(shift_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `alert_id` | TEXT | yes |  | Primary key. |
| `alert_type` | TEXT | yes | WRONG_STORE, MISSING_REASON, COUNT_BEFORE_MOVEMENTS, TRANSFER_DOUBLE_LOSS, REPEATED_ADJUSTMENTS, UNEXPLAINED_LOSS | Rule that fired. |
| `classification` | TEXT | yes | DATA_ERROR, PROCESS_ERROR, SUSPECTED_THEFT | What kind of problem it most likely is. |
| `store_id` | TEXT | yes |  | FK -> store. |
| `sku_id` | TEXT | no |  | FK -> sku, when the alert is about one product. |
| `employee_id` | TEXT | no |  | FK -> employee linked to the evidence. |
| `role_id` | TEXT | no |  | FK -> role the employee worked in. |
| `shift_id` | TEXT | no |  | FK -> shift of the key evidence. |
| `first_evidence_ts` | TIMESTAMP | yes |  | Earliest evidence. |
| `last_evidence_ts` | TIMESTAMP | yes |  | Latest evidence. |
| `detected_ts` | TIMESTAMP | yes |  | last_evidence_ts + 1 h. |
| `loss_units` | INTEGER | yes |  | Units at stake. >= 0. |
| `loss_value_inr` | REAL | yes |  | loss_units x unit_cost, INR. |
| `risk_score` | REAL | yes |  | 0-100. Base score per rule + value at stake. Calculated. |
| `severity` | TEXT | yes | LOW, MEDIUM, HIGH | HIGH >= 70, MEDIUM >= 40, else LOW. |
| `reason_text` | TEXT | yes |  | Plain-English reasons built only from the evidence numbers. |

## alert_evidence

Bridge: records that back each alert (many-to-many).

**Primary key:** `alert_id, evidence_type, evidence_id`
<br>**FK:** `alert_id` → `shrinkage_alert(alert_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `alert_id` | TEXT | yes |  | FK -> shrinkage_alert. |
| `evidence_type` | TEXT | yes | MOVEMENT, CYCLE_COUNT, TRANSFER | Which table evidence_id points to. |
| `evidence_id` | TEXT | yes |  | movement_id, count_id or transfer_id. |

## investigation

A case opened for an alert and assigned to the store manager.

**Primary key:** `investigation_id` — format `INV-\d{4}-\d{6}`
<br>**FK:** `alert_id` → `shrinkage_alert(alert_id)`
<br>**FK:** `store_id` → `store(store_id)`
<br>**FK:** `assigned_employee_id` → `employee(employee_id)`


| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `investigation_id` | TEXT | yes |  | Primary key. |
| `alert_id` | TEXT | yes |  | FK -> shrinkage_alert. One case per alert. |
| `store_id` | TEXT | yes |  | FK -> store. |
| `assigned_employee_id` | TEXT | yes |  | FK -> employee (the store manager). |
| `investigation_type` | TEXT | yes | LOSS_PREVENTION, DATA_CORRECTION, PROCESS_COACHING | Follows the alert classification. |
| `priority` | TEXT | yes | LOW, MEDIUM, HIGH | Same as alert severity. |
| `status` | TEXT | yes | OPEN | All new cases start OPEN. |
| `opened_ts` | TIMESTAMP | yes |  | detected_ts + 2 h. |
| `recommended_action` | TEXT | yes |  | Next step for the investigator. |

## ground_truth/anomalies (answer key)

Answer key, kept in a separate folder. The detector never reads it.

| Field | Type | Required | Allowed values | Meaning / units / rule |
|---|---|---|---|---|
| `gt_id` | TEXT | yes |  | Primary key, GT-0001... |
| `anomaly_type` | TEXT | yes |  | What was planted (matches alert_type) or DECOY_DAMAGE_EVENT. |
| `label` | TEXT | yes | ANOMALY, DECOY | ANOMALY = should be flagged; DECOY = innocent, must not be called theft. |
| `entity_type` | TEXT | yes | MOVEMENT, CYCLE_COUNT, TRANSFER, EMPLOYEE, STORE_DAY | What a correct alert must point at. |
| `entity_id` | TEXT | yes |  | The ID a correct alert must point at. |
| `store_id` | TEXT | yes |  | Store involved. |
| `employee_id` | TEXT | no |  | Employee involved, if any. |
| `related_ids` | TEXT | no |  | Other rows touched by the planted case, ';'-separated. |
| `description` | TEXT | yes |  | What was changed and why it is wrong. |
