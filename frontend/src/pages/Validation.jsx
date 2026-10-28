import React, { useState } from "react";
import { api, useLoad } from "../api.js";
import { Card, Loading, Status, Table, checkKind, fmt } from "../components/ui.jsx";

export default function Validation({ size }) {
  const state = useLoad(() => api.validation(size), [size]);
  const [show, setShow] = useState("all");
  return (
    <Loading state={state}>
      {(v) => {
        const rows = v.checks.filter((c) => show === "all" || (show === "issues" ? c.status !== "PASS" : c.category === show));
        const passed = v.checks.filter((c) => c.status === "PASS").length;
        return (
          <Card
            title="Validation checks"
            subtitle={<>{passed} of {v.checks.length} pass ·{" "}
              <Status kind={v.integrity_passed ? "good" : "critical"}>{v.integrity_passed ? "integrity passed" : "integrity failed"}</Status>{" "}
              · business-rule checks are expected to flag exactly the planted data errors</>}
            actions={
              <div className="seg">
                {[["all", "All"], ["issues", "Flagged"], ["integrity", "Integrity"], ["business_rule", "Business rules"]].map(([k, l]) => (
                  <button key={k} className={show === k ? "on" : ""} onClick={() => setShow(k)}>{l}</button>
                ))}
              </div>
            }
          >
            <Table
              rows={rows}
              columns={[
                { key: "check", label: "Check" },
                { key: "category", label: "Category", render: (r) => fmt.label(r.category) },
                { key: "failing_rows", label: "Rows flagged", num: true, render: (r) => fmt.n(r.failing_rows) },
                { key: "status", label: "Status", render: (r) => <Status kind={checkKind[r.status]}>{fmt.label(r.status)}</Status> },
              ]}
            />
          </Card>
        );
      }}
    </Loading>
  );
}
