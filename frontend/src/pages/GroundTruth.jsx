import React from "react";
import { api, useLoad } from "../api.js";
import { Card, Chip, Loading, Status, Table, fmt, outcomeKind } from "../components/ui.jsx";

// The answer key is only shown here, for evaluation. The detector never reads it.
export default function GroundTruth({ size, onOpenAlert }) {
  const state = useLoad(() => api.groundTruth(size), [size]);
  return (
    <Loading state={state}>
      {(rows) => (
        <Card title="Answer key" subtitle="Every planted case and whether the detector caught it. Decoys are innocent and must not be called theft.">
          <Table
            rows={rows}
            onRow={(r) => r.alert_ids[0] && onOpenAlert(r.alert_ids[0])}
            columns={[
              { key: "gt_id", label: "Case" },
              { key: "anomaly_type", label: "Type", render: (r) => fmt.label(r.anomaly_type) },
              { key: "label", label: "Label", render: (r) => <Chip>{fmt.label(r.label)}</Chip> },
              { key: "entity_id", label: "Points at" },
              { key: "description", label: "What was planted" },
              { key: "outcome", label: "Outcome", render: (r) => <Status kind={outcomeKind[r.outcome]}>{fmt.label(r.outcome)}</Status> },
            ]}
          />
        </Card>
      )}
    </Loading>
  );
}
