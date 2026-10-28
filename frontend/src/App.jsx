import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import Alerts from "./pages/Alerts.jsx";
import GroundTruth from "./pages/GroundTruth.jsx";
import Overview from "./pages/Overview.jsx";
import Validation from "./pages/Validation.jsx";
import { Status, fmt } from "./components/ui.jsx";

const TABS = [["overview", "Overview"], ["alerts", "Alerts"], ["validation", "Validation"], ["truth", "Answer key"]];

export default function App() {
  const [runs, setRuns] = useState([]);
  const [size, setSize] = useState(null);
  const [tab, setTab] = useState("overview");
  const [preset, setPreset] = useState({});
  const [focus, setFocus] = useState(0);   // bumps to remount pages after a run
  const [msg, setMsg] = useState(null);
  const [health, setHealth] = useState(null);

  const refreshRuns = () => api.runs().then((r) => {
    setRuns(r);
    setSize((s) => s ?? (r.find((x) => x.available) || r[0]).size);   // smallest built dataset first
    return r;
  }).catch((e) => setMsg(e.message));
  useEffect(() => { refreshRuns(); api.health().then(setHealth).catch(() => {}); }, []);

  const running = runs.find((r) => r.state === "running");
  useEffect(() => {   // poll only while a run is in progress
    if (!running) return;
    const t = setInterval(() => refreshRuns().then((r) => {
      const done = r?.find((x) => x.size === running.size);
      if (done && done.state !== "running") {
        setMsg(done.state === "done" ? `${running.size} run finished` : `Run failed: ${done.error}`);
        setFocus((f) => f + 1);
      }
    }), 2000);
    return () => clearInterval(t);
  }, [running?.size]);

  const start = (repro) => api.startRun(size, repro).then(() => { setMsg(null); refreshRuns(); }).catch((e) => setMsg(e.message));
  const current = runs.find((r) => r.size === size);
  const openAlerts = (p) => { setPreset({ alert_type: "", classification: "", severity: "", store_id: "", q: "", ...p }); setTab("alerts"); };

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden="true">◧</span>
          <div>
            <h1>Shrinkage Monitor</h1>
            <p className="muted small">Synthetic retail stock ledger · rule-based loss detection · scored against an answer key
              {health && size && <> · data: {health.storage.kind === "postgres" ? `Postgres (${health.storage.schema_prefix}_${size})` : "local SQLite"}</>}</p>
          </div>
        </div>
        <div className="controls">
          <div className="seg" role="tablist" aria-label="Dataset size">
            {(runs.some((r) => r.available) ? runs.filter((r) => r.available) : runs).map((r) => (   // only built datasets
              <button key={r.size} className={size === r.size ? "on" : ""} onClick={() => setSize(r.size)}>
                {fmt.label(r.size)} {r.available && <span className="muted small">{fmt.n(r.movements)} rows</span>}
              </button>
            ))}
          </div>
          <button onClick={() => start(false)} disabled={!!running || !size}>Run pipeline</button>
          <button className="ghost" onClick={() => start(true)} disabled={!!running || !size} title="Runs twice and compares checksums">
            + reproducibility check
          </button>
        </div>
      </header>

      {(running || msg) && (
        <div className="banner">
          {running ? <Status kind="warning">Running {running.size} pipeline{running.repro ? " twice (reproducibility check)" : ""} since {running.started_at}{running.step ? ` · ${running.step}` : ""}…</Status> : msg}
        </div>
      )}

      <nav className="tabs">
        {TABS.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
      </nav>

      <main key={`${size}-${focus}`}>
        {!size ? <div className="empty">Connecting to the API…</div>
          : !current?.available ? <div className="empty">No {size} run yet. Click “Run pipeline”.</div>
          : tab === "overview" ? <Overview size={size} onOpenAlerts={openAlerts} />
          : tab === "alerts" ? <Alerts size={size} preset={preset} />
          : tab === "validation" ? <Validation size={size} />
          : <GroundTruth size={size} onOpenAlert={(id) => openAlerts({ q: id })} />}
      </main>
    </div>
  );
}
