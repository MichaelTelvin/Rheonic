export interface Incident {
  id: string;
  projectId: string;
  incidentType: string;
  status: string;
  createdAt: string;
  evidence: Record<string, unknown>;
}
