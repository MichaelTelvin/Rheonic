import { frontendConfig } from "../config";

export interface RealtimeMetrics {
  requests_60s: number;
  tokens_60s: number;
}

export interface IncidentItem {
  id: string;
  type: string;
  severity: "low" | "medium" | "high" | string;
  status: "open" | "resolved" | string;
  created_at: string;
  resolved_at: string | null;
  evidence: Record<string, unknown>;
}

export interface ProjectItem {
  id: string;
  name: string;
  created_at: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${frontendConfig.apiBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function fetchMetrics(projectId: string): Promise<RealtimeMetrics> {
  return request<RealtimeMetrics>(`/api/v1/metrics/realtime?project_id=${encodeURIComponent(projectId)}`);
}

export async function fetchIncidents(projectId: string): Promise<IncidentItem[]> {
  return request<IncidentItem[]>(`/api/v1/incidents?project_id=${encodeURIComponent(projectId)}`);
}

export async function resolveIncident(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/v1/incidents/${encodeURIComponent(id)}/resolve`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function fetchProjects(): Promise<ProjectItem[]> {
  return request<ProjectItem[]>("/api/v1/projects");
}
