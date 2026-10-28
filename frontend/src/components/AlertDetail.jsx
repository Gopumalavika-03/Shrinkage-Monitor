import React, { useState } from "react";
import { api, useLoad } from "../api.js";
import { Card, Chip, Loading, Status, Table, fmt, severityKind } from "./ui.jsx";

export default function AlertDetail({ size, id, onClose }) {
  const state = useLoad(() => api.alert(size, id), [size, id]);
  return (
    <aside className="detail">
      <Loading state={state}>{(a) => <Body a={a} size={size} onClose={onClose} />}</Loading>
    </aside>
  );
}

function Fact({ label, children }) {
  return <div className="fact"><div className="muted small">{label}</div><div>{children ?? "–"}</div></div>;
}

function Explain({ size, id }) {
  const [s, setS] = useState({ busy: false });
  const run = () => {
    setS({ busy: true });
    api.explain(size, id).then((r) => setS({ result: r })).catch((e) => setS({ error: e.message }));
  };
  return (
    <div className="explain">
      <button onClick={run} disabled={s.busy}>{s.busy ? "Asking the LLM…" : "Explain in plain English (LLM)"}</button>
      {s.result && <p className="llm-text">{s.result.text} <span className="muted small">— {s.result.model}{s.result.cached ? ", cached" : ""}</span></p>}
      {s.error && <p className="muted small">{s.error}</p>}
    </div>
  );
}

function Body({ a, size, onClose }) {
  const inv = a.investigation;
  const ev = a.evidence;
  return (
    <Card
      title={a.alert_id}
      subtitle={`${fmt.label(a.alert_type)} · ${a.store_name}, ${a.city}`}
      actions={<button className="ghost" onClick={onClose} aria-label="Close">✕</button>}
    >
      <div className="row gap">
        <Status kind={severityKind[a.severity]}>{fmt.label(a.severity)} · risk {a.risk_score}</Status>
        <Chip>{fmt.label(a.classification)}</Chip>
        {a.ground_truth_match.length
          ? <Status kind="good">Matches planted case {a.ground_truth_match[0].gt_id}</Status>
          : <Status kind="warning">No planted case matches</Status>}
      </div>

      <p className="reason">{a.reason_text}</p>
      <Explain size={size} id={a.alert_id} />

      <div className="facts">
        <Fact label="Employee">{a.employee_name ? `${a.employee_name} · ${a.employee_id}` : null}</Fact>
        <Fact label="Role">{a.role_name}</Fact>
        <Fact label="Shift">{a.shift_id}</Fact>
        <Fact label="SKU">{a.sku_id}</Fact>
        <Fact label="Units at stake">{fmt.n(a.loss_units)}</Fact>
        <Fact label="Value at stake">{fmt.inr(a.loss_value_inr)}</Fact>
        <Fact label="Evidence window">{a.first_evidence_ts} → {a.last_evidence_ts}</Fact>
        <Fact label="Detected">{a.detected_ts}</Fact>
      </div>

      {inv && (
        <div className="investigation">
          <h3>Investigation {inv.investigation_id}</h3>
          <p>
            <Chip>{fmt.label(inv.investigation_type)}</Chip> <Chip>{inv.status}</Chip>{" "}
            <span className="muted">assigned to {inv.assigned_name} (store manager)</span>
          </p>
          <p className="small">{inv.recommended_action}</p>
        </div>
      )}

      {a.ground_truth_match.length > 0 && (
        <p className="muted small">Answer key: {a.ground_truth_match[0].description}</p>
      )}

      <h3>Evidence ({ev.total} records)</h3>
      {ev.transfers.length > 0 && (
        <Table rows={ev.transfers} columns={[
          { key: "transfer_id", label: "Transfer" }, { key: "from_store_id", label: "From" },
          { key: "to_store_id", label: "To" }, { key: "quantity", label: "Qty", num: true }, { key: "status", label: "Status" },
        ]} />
      )}
      {ev.cycle_counts.length > 0 && (
        <Table rows={ev.cycle_counts} columns={[
          { key: "count_id", label: "Count" }, { key: "sku_name", label: "SKU" },
          { key: "system_qty_as_of_ts", label: "Book time" }, { key: "count_ts", label: "Counted" },
          { key: "expected_qty", label: "Expected", num: true }, { key: "counted_qty", label: "Counted", num: true },
          { key: "variance_qty", label: "Variance", num: true },
        ]} />
      )}
      {ev.movements.length > 0 && (
        <Table rows={ev.movements} columns={[
          { key: "movement_id", label: "Movement" }, { key: "movement_ts", label: "Time" },
          { key: "movement_type", label: "Type", render: (r) => fmt.label(r.movement_type) },
          { key: "sku_name", label: "SKU" }, { key: "quantity", label: "Qty", num: true },
          { key: "reason_code", label: "Reason", render: (r) => r.reason_code ?? (r.movement_type === "ADJUSTMENT" ? <Status kind="warning">none</Status> : "–") },
          { key: "employee_id", label: "By" },
        ]} />
      )}
    </Card>
  );
}
