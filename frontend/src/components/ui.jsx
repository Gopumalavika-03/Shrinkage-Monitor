import React, { useState } from "react";

export const fmt = {
  n: (v) => (v == null ? "–" : Number(v).toLocaleString("en-IN")),
  inr: (v) => (v == null ? "–" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`),
  pct: (v) => (v == null ? "–" : `${Math.round(v * 100)}%`),
  label: (s) => (s ? s.replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : "–"),
};

export function Kpi({ label, value, hint }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}

// Status always ships with an icon + label, never colour alone.
const STATUS = {
  good: "✓", warning: "!", serious: "▲", critical: "✕", neutral: "•",
};
export function Status({ kind = "neutral", children }) {
  return (
    <span className={`status status-${kind}`}>
      <span aria-hidden="true">{STATUS[kind]}</span> {children}
    </span>
  );
}

export const severityKind = { HIGH: "critical", MEDIUM: "serious", LOW: "warning" };
export const checkKind = { PASS: "good", FLAGGED: "warning", FAIL: "critical" };
export const outcomeKind = { CAUGHT: "good", CORRECTLY_IGNORED: "good", MISSED: "critical", WRONGLY_FLAGGED: "critical" };

export function Chip({ children }) {
  return <span className="chip">{children}</span>;
}

export function Card({ title, subtitle, children, actions }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p className="muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Loading({ state, children }) {
  if (state.loading && !state.data) return <div className="empty">Loading…</div>;
  if (state.error) return <div className="empty error">{state.error.message}</div>;
  return children(state.data);
}

/** Horizontal bars from a zero baseline. rows: [{label, value, tip, tone}] tone: "pos" | "neg" | undefined.
 *  Signed values put negatives left of the axis (diverging), otherwise one hue. Hover shows a tooltip. */
export function BarList({ rows, format = fmt.n, onSelect }) {
  const [tip, setTip] = useState(null);
  const signed = rows.some((r) => r.value < 0);
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  return (
    <div className="bars" onMouseLeave={() => setTip(null)}>
      {rows.map((r) => {
        const w = `${(Math.abs(r.value) / max) * (signed ? 50 : 100)}%`;
        const neg = r.value < 0;
        return (
          <div
            key={r.label}
            className={`bar-row ${onSelect ? "clickable" : ""}`}
            onClick={onSelect ? () => onSelect(r) : undefined}
            onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY, text: r.tip || `${r.label}: ${format(r.value)}` })}
          >
            <div className="bar-label">{r.label}</div>
            <div className={`bar-track ${signed ? "signed" : ""}`}>
              {signed && <div className="bar-axis" />}
              <div
                className={`bar ${neg ? "bar-neg" : r.tone === "neutral" ? "bar-neutral" : "bar-pos"}`}
                style={signed ? { width: w, [neg ? "right" : "left"]: "50%" } : { width: w }}
              />
            </div>
            <div className="bar-value">{format(r.value)}</div>
          </div>
        );
      })}
      {tip && <div className="tooltip" style={{ left: tip.x + 12, top: tip.y + 12 }}>{tip.text}</div>}
    </div>
  );
}

export function Table({ columns, rows, onRow, selected, empty = "Nothing to show" }) {
  if (!rows?.length) return <div className="empty">{empty}</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : ""}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={r[columns[0].key] ?? i}
              onClick={onRow ? () => onRow(r) : undefined}
              className={`${onRow ? "clickable" : ""} ${selected && selected === r[columns[0].key] ? "selected" : ""}`}
            >
              {columns.map((c) => (
                <td key={c.key} className={c.num ? "num" : ""}>{c.render ? c.render(r) : r[c.key] ?? "–"}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
