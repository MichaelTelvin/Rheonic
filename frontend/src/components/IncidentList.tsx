import type { Incident } from "../types/incident";

export interface IncidentListProps {
  incidents: Incident[];
}

export function IncidentList(_props: IncidentListProps): JSX.Element {
  // TODO: Render incident collection with sorting/filter options.
  return <section />;
}
