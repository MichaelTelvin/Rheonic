import { frontendConfig } from "../config";

export interface RealtimeMetrics {
  requests_60s: number;
  tokens_60s: number;
}

export interface ProtectMetrics {
  warn_60m: number;
  block_60m: number;
  last: {
    decision: string;
    reason: string;
    ts: string;
  } | null;
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

export interface ProjectProtectSettings {
  protect_enabled: boolean;
  protect_fail_mode: "open" | "closed" | string;
  protect_max_req_per_min: number | null;
  protect_max_tok_per_min: number | null;
  protect_decision_timeout_ms: number;
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

export interface AuthUser {
  id: string;
  email: string;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = window.localStorage.getItem(frontendConfig.authTokenStorageKey);
  const headers = new Headers(init?.headers ?? {});
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${frontendConfig.apiBaseUrl}${path}`, {
    headers,
    ...init,
  });

  let responseMessage = `Request failed: ${response.status}`;
  let responseCode: string | undefined;
  try {
    const errorBody = (await response.clone().json()) as {
      error?: { code?: string; message?: string };
      detail?: string;
    };
    if (errorBody.error?.message) {
      responseMessage = errorBody.error.message;
      responseCode = errorBody.error.code;
    } else if (typeof errorBody.detail === "string" && errorBody.detail) {
      responseMessage = errorBody.detail;
    }
  } catch {
    // ignore non-json error payloads
  }

  if (response.status === 401) {
    unauthorizedHandler?.();
    throw new ApiError(response.status, responseMessage, responseCode);
  }

  if (!response.ok) {
    throw new ApiError(response.status, responseMessage, responseCode);
  }

  return (await response.json()) as T;
}

export async function register(email: string, password: string): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function fetchMetrics(projectId: string): Promise<RealtimeMetrics> {
  return request<RealtimeMetrics>(`/api/v1/metrics/realtime?project_id=${encodeURIComponent(projectId)}`);
}

export async function fetchProtectMetrics(projectId: string): Promise<ProtectMetrics> {
  return request<ProtectMetrics>(`/api/v1/metrics/protect?project_id=${encodeURIComponent(projectId)}`);
}

export async function fetchProjectProtect(projectId: string): Promise<ProjectProtectSettings> {
  return request<ProjectProtectSettings>(`/api/v1/projects/${encodeURIComponent(projectId)}/protect`);
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
