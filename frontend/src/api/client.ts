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

export interface IngestKeyItem {
  id: string;
  name: string;
  last4: string | null;
  status: "active" | "revoked" | string;
  created_at: string;
  revoked_at: string | null;
}

export interface CreateKeyResponse {
  key: string;
  key_id: string;
  name: string;
  last4: string | null;
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

export async function createProject(name: string): Promise<ProjectItem> {
  return request<ProjectItem>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function listKeys(projectId: string): Promise<IngestKeyItem[]> {
  return request<IngestKeyItem[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/keys`);
}

export async function createKey(projectId: string, name: string): Promise<CreateKeyResponse> {
  return request<CreateKeyResponse>(`/api/v1/projects/${encodeURIComponent(projectId)}/keys`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function revokeKey(keyId: string): Promise<IngestKeyItem> {
  return request<IngestKeyItem>(`/api/v1/keys/${encodeURIComponent(keyId)}/revoke`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function rotateKey(keyId: string): Promise<CreateKeyResponse> {
  return request<CreateKeyResponse>(`/api/v1/keys/${encodeURIComponent(keyId)}/rotate`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
