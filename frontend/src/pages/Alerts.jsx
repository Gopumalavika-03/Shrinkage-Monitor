import React, { useEffect, useState } from "react";
import { api, useLoad } from "../api.js";
import AlertDetail from "../components/AlertDetail.jsx";
import { Card, Chip, Loading, Status, Table, fmt, severityKind } from "../components/ui.jsx";

const TYPES = ["", "WRONG_STORE", "MISSING_REASON", "COUNT_BEFORE_MOVEMENTS", "TRANSFER_DOUBLE_LOSS",
  "REPEATED_ADJUSTMENTS", "UNEXPLAINED_LOSS"];
const CLASSES = ["", "SUSPECTED_THEFT", "DATA_ERROR", "PROCESS_ERROR"];
const SEVERITIES = ["", "HIGH", "MEDIUM", "LOW"];
const PAGE = 25;

function Select({ label, value, options, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o} value={o}>{o ? fmt.label(o) : "All"}</option>)}
      </select>
    </label>
  );
}

export default function Alerts({ size, preset }) {
  const [filters, setFilters] = useState({ alert_type: "", classification: "", severity: "", store_id: "", q: "", ...preset });
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  useEffect(() => { setFilters((f) => ({ ...f, ...preset })); setOffset(0); }, [preset]);

  const set = (k) => (v) => { setFilters((f) => ({ ...f, [k]: v })); setOffset(0); };
  const state = useLoad(() => api.alerts(size, { ...filters, limit: PAGE, offset }), [size, JSON.stringify(filters), offset]);

  return (
    <div className={`alerts-layout ${selected ? "with-detail" : ""}`}>
      <Card title="Shrinkage alerts" subtitle="Sorted by risk score. Click an alert for its evidence.">
        <div className="filters">
          <Select label="Rule" value={filters.alert_type} options={TYPES} onChange={set("alert_type")} />
          <Select label="Classification" value={filters.classification} options={CLASSES} onChange={set("classification")} />
          <Select label="Severity" value={filters.severity} options={SEVERITIES} onChange={set("severity")} />
          <label className="field">
            <span>Store</span>
            <input value={filters.store_id} placeholder="STORE-000001" onChange={(e) => set("store_id")(e.target.value.trim())} />
          </label>
          <label className="field grow">
            <span>Search</span>
            <input value={filters.q} placeholder="alert, employee, SKU or text" onChange={(e) => set("q")(e.target.value)} />
          </label>
        </div>
        <Loading state={state}>
          {(d) => (
            <>
              <Table
                selected={selected}
                onRow={(r) => setSelected(r.alert_id)}
                rows={d.items}
                empty="No alerts match these filters"
                columns={[
                  { key: "alert_id", label: "Alert" },
                  { key: "alert_type", label: "Rule", render: (r) => fmt.label(r.alert_type) },
                  { key: "classification", label: "Class", render: (r) => <Chip>{fmt.label(r.classification)}</Chip> },
                  { key: "store_id", label: "Store" },
                  { key: "employee_id", label: "Employee", render: (r) => r.employee_name ? `${r.employee_name} (${r.role_name})` : "–" },
                  { key: "loss_value_inr", label: "At stake", num: true, render: (r) => fmt.inr(r.loss_value_inr) },
                  { key: "risk_score", label: "Risk", num: true },
                  { key: "severity", label: "Severity", render: (r) => <Status kind={severityKind[r.severity]}>{fmt.label(r.severity)}</Status> },
                ]}
              />
              <div className="pager">
                <span className="muted">{d.total ? `${d.offset + 1}–${Math.min(d.offset + PAGE, d.total)} of ${d.total}` : ""}</span>
                <button disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>Previous</button>
                <button disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
            </>
          )}
        </Loading>
      </Card>
      {selected && <AlertDetail size={size} id={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
