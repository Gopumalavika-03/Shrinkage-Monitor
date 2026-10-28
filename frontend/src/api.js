// Thin wrapper over the FastAPI backend. Errors carry the server's `detail` message.
import { useCallback, useEffect, useState } from "react";

// Empty = same origin (dev proxy or FastAPI serving the build). Set VITE_API_BASE_URL in frontend/.env otherwise.
const BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function request(path, options = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`);
  return body;
}

const qs = (params) => {
  const p = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null));
  return p.toString() ? `?${p}` : "";
};

export const api = {
  health: () => request("/health"),
  runs: () => request("/runs"),
  startRun: (size, repro = false) => request("/runs", { method: "POST", body: JSON.stringify({ size, repro }) }),
  overview: (size) => request(`/${size}/overview`),
  alerts: (size, params) => request(`/${size}/alerts${qs(params)}`),
  alert: (size, id) => request(`/${size}/alerts/${id}`),
  explain: (size, id) => request(`/${size}/alerts/${id}/explain`, { method: "POST" }),
  validation: (size) => request(`/${size}/validation`),
  groundTruth: (size) => request(`/${size}/ground-truth`),
};

// Run an async loader whenever `deps` change; returns { data, error, loading, reload }.
export function useLoad(loader, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    loader()
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(load, [load]);
  return { ...state, reload: load };
}
