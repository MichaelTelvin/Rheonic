export interface Incident {
  id: string;
  projectId: string;
  incidentType: string;
  severity: string;
  createdAt: string;
  evidence: Record<string, unknown>;
}
