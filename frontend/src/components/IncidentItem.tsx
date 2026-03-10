import { useState } from "react";

import type { IncidentItem as Incident } from "../api/client";
import { formatRelative, formatTime, humanizeIncidentType } from "../pages/dashboardUtils";
import { Badge } from "./Badge";
import { Card } from "./Card";

export interface IncidentItemProps {
  incident: Incident;
  resolving: boolean;
  onResolve: (incidentId: string) => Promise<void>;
}

function formatEvidenceValue(value: unknown): unknown {
  if (typeof value === "string") {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime()) && /[tT]/.test(value)) {
      return `${parsed.toLocaleDateString()} ${parsed.toLocaleTimeString()}`;
    }
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((entry) => formatEvidenceValue(entry));
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, formatEvidenceValue(entry)]),
    );
  }

  return value;
}

export function IncidentItem({ incident, resolving, onResolve }: IncidentItemProps): JSX.Element {
  const [showDetails, setShowDetails] = useState<boolean>(false);
  const canResolve = incident.status === "open";
  // Show evidence timestamps in the viewer's local timezone while keeping the raw values stored in backend state.
  const formattedEvidence = formatEvidenceValue(incident.evidence);

  return (
    <Card>
      <div className="incident-head">
        <p className="incident-title">{humanizeIncidentType(incident.type)}</p>
        <Badge value={incident.status} kind="status" />
      </div>

      <p className="incident-meta">
        <span className="incident-meta-relative">{formatRelative(incident.created_at)}</span>
        <span>· Created {formatTime(incident.created_at)}</span>
      </p>
      <p className="incident-meta">
        <span>Provider {(incident.evidence.provider as string | undefined) ?? "unknown"}</span>
        <span>· Count {String((incident.evidence.count as number | undefined) ?? 1)}</span>
      </p>

      <div className="incident-actions">
        <button onClick={() => setShowDetails((value) => !value)}>{showDetails ? "Hide details" : "Show details"}</button>
        <button className="resolve" onClick={() => void onResolve(incident.id)} disabled={resolving || !canResolve}>
          {canResolve ? (resolving ? "Resolving..." : "Resolve") : "Resolved"}
        </button>
      </div>

      {showDetails ? <pre>{JSON.stringify(formattedEvidence, null, 2)}</pre> : null}
    </Card>
  );
}
