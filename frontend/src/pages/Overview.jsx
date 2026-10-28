import React from "react";
import { api, useLoad } from "../api.js";
import { BarList, Card, Kpi, Loading, Status, Table, checkKind, fmt } from "../components/ui.jsx";

const INNOCENT = [
  ["decoy_damage_event_rows", "decoy_rows_in_theft_alerts", "One-day damage incident rows (decoys)"],
  ["damaged_return_writeoffs", "damaged_return_writeoffs_in_theft_alerts", "Damaged customer returns written off"],
  ["honest_transit_losses", "honest_transit_losses_flagged", "Honest transit losses (written off once)"],
  ["honest_large_count_shortages", "honest_large_shortages_in_theft_alerts", "Large shortages with no staff pattern"],
];

export default function Overview({ size, onOpenAlerts }) {
  const state = useLoad(() => api.overview(size), [size]);
  return <Loading state={state}>{(o) => <Body o={o} onOpenAlerts={onOpenAlerts} />}</Loading>;
}

function Body({ o, onOpenAlerts }) {
  const ev = o.evaluation;
  const rc = o.row_counts;
  const eq = o.stock_equation;
  const theft = o.alerts_by_type.filter((a) => a.classification === "SUSPECTED_THEFT").reduce((s, a) => s + a.alerts, 0);
  return (
    <div className="stack">
      <div className="kpis">
        <Kpi label="Stock movements" value={fmt.n(rc.inventory_movement)} hint={`${fmt.n(rc.store)} stores · ${fmt.n(rc.sku)} SKUs`} />
        <Kpi label="Cycle counts" value={fmt.n(rc.cycle_count)} hint={`${fmt.n(rc.shift)} shifts`} />
        <Kpi label="Alerts raised" value={fmt.n(rc.shrinkage_alert)} hint={`${theft} suspected theft`} />
        <Kpi label="Precision / recall" value={`${fmt.pct(ev.overall.precision)} / ${fmt.pct(ev.overall.recall)}`}
             hint={`${ev.overall.tp} caught · ${ev.overall.fp} false · ${ev.overall.fn} missed`} />
        <Kpi label="Integrity checks" value={`${o.checks.passed}/${o.checks.total}`}
             hint={o.integrity_passed ? "all integrity checks pass" : "integrity FAILED"} />
      </div>

      <div className="grid-2">
        <Card title="Detection vs answer key" subtitle="Each planted case scored at the unit a correct alert must point at.">
          <Table
            columns={[
              { key: "anomaly_type", label: "Planted case", render: (r) => fmt.label(r.anomaly_type) },
              { key: "unit", label: "Unit", render: (r) => fmt.label(r.unit) },
              { key: "planted", label: "Planted", num: true },
              { key: "flagged", label: "Flagged", num: true },
              { key: "precision", label: "Precision", num: true, render: (r) => fmt.pct(r.precision) },
              { key: "recall", label: "Recall", num: true, render: (r) => fmt.pct(r.recall) },
            ]}
            rows={ev.per_type}
            onRow={(r) => onOpenAlerts({ alert_type: r.anomaly_type })}
          />
        </Card>

        <Card title="Innocent losses are not called theft" subtitle="Records with an honest explanation that appear as theft evidence.">
          <Table
            columns={[
              { key: "label", label: "Innocent loss" },
              { key: "total", label: "In data", num: true, render: (r) => fmt.n(r.total) },
              { key: "hit", label: "In theft alerts", num: true,
                render: (r) => <Status kind={r.hit === 0 ? "good" : "warning"}>{fmt.n(r.hit)}</Status> },
            ]}
            rows={INNOCENT.map(([t, h, label]) => ({ label, total: ev.innocent_checks[t], hit: ev.innocent_checks[h] }))}
          />
          <p className="muted small">A non-zero last row means a background shortage happened on stock a real planted suspect handled.</p>
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Stock equation (all stores, units)"
              subtitle={<>opening + receipts − sales ± transfers + returns ± adjustments = closing book{" "}
                <Status kind={eq.balances ? "good" : "critical"}>{eq.balances ? "balances" : "does not balance"}</Status></>}>
          <BarList rows={[
            { label: "Opening", value: eq.opening, tone: "neutral" },
            { label: "Receipts", value: eq.receipts },
            { label: "Sales", value: eq.sales },
            { label: "Transfers in", value: eq.transfers_in },
            { label: "Transfers out", value: eq.transfers_out },
            { label: "Returns", value: eq.returns },
            { label: "Adjustments", value: eq.adjustments },
            { label: "Closing book", value: eq.closing_book, tone: "neutral" },
          ]} />
          <p className="muted small">Blue adds stock, red removes it. Checked per count and per store-SKU too, not only in total.</p>
        </Card>

        <Card title="Write-offs by reason (units)" subtitle="Where adjustments took stock out. MISSING = planted adjustments with no reason.">
          <BarList rows={Object.entries(eq.adjustments_by_reason)
            .map(([k, v]) => ({ label: fmt.label(k), value: v }))
            .sort((a, b) => a.value - b.value)} />
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Alerts by rule" subtitle="Click a bar to see those alerts.">
          <BarList
            onSelect={(r) => onOpenAlerts({ alert_type: r.id })}
            rows={o.alerts_by_type.map((a) => ({
              id: a.alert_type, label: fmt.label(a.alert_type), value: a.alerts,
              tip: `${fmt.label(a.alert_type)} · ${a.alerts} alerts · ${fmt.inr(a.loss_value_inr)} at stake · ${fmt.label(a.classification)}`,
            }))}
          />
        </Card>
        <Card title="Stores with the most value at stake">
          <Table
            columns={[
              { key: "store_id", label: "Store" },
              { key: "store_name", label: "Name" },
              { key: "alerts", label: "Alerts", num: true },
              { key: "theft_alerts", label: "Theft", num: true },
              { key: "loss_value_inr", label: "At stake", num: true, render: (r) => fmt.inr(r.loss_value_inr) },
            ]}
            rows={o.top_stores}
            onRow={(r) => onOpenAlerts({ store_id: r.store_id })}
          />
        </Card>
      </div>

      <Card title="Reproducibility">
        <div className="repro">
          <div><span className="muted">Seed</span> <code>{o.seed}</code></div>
          <div><span className="muted">Combined SHA-256</span> <code>{o.combined_sha256.slice(0, 24)}…</code></div>
          {o.reproducibility ? (
            <Status kind={o.reproducibility.identical ? "good" : "critical"}>
              {o.reproducibility.identical ? `Second run identical (${o.reproducibility.files_compared} files)` : "Runs differ"}
            </Status>
          ) : (
            <Status kind="neutral">Not checked — use “Run pipeline” with the reproducibility check</Status>
          )}
          <div><span className="muted">SQLite FK violations</span> <Status kind={checkKind[o.sqlite_foreign_key_violations === 0 ? "PASS" : "FAIL"]}>{o.sqlite_foreign_key_violations}</Status></div>
        </div>
      </Card>
    </div>
  );
}
