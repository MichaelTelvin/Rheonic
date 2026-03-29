import { frontendConfig } from "../config";

export interface RealtimeMetrics {
  requests_60s: number;
  tokens_60s: number;
}

export interface ProtectMetrics {
  allowed_60m: number;
  warned_60m: number;
  blocked_60m: number;
  decision_timeouts_60m: number;
  decision_latency_p50_60m_ms: number | null;
  decision_latency_p95_60m_ms: number | null;
  last: {
    decision: string;
    reason: string;
    ts: string;
  } | null;
}

export interface ProtectHealthMetrics {
  p50_ms: number | null;
  p95_ms: number | null;
  timeouts_30m: number;
  timeouts_60m: number;
}

export interface DeliveryFailures {
  count: number;
  last_attempt_at: string | null;
}

export interface IncidentItem {
  id: string;
  type: string;
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

export interface ProjectProvidersResponse {
  providers: string[];
}

export interface ProjectProtectSettings {
  protect_enabled: boolean;
  protect_fail_mode: "open" | "closed" | string;
  apply_clamp: boolean;
  protect_max_req_per_min: number | null;
  protect_max_tok_per_min: number | null;
}

export interface ProjectWebhookSettings {
  enabled: boolean;
  email_enabled: boolean;
  url: string | null;
  last_status: "success" | "failed" | string | null;
  last_at: string | null;
  last_error: string | null;
}

export interface UpdateProjectWebhookInput {
  enabled: boolean;
  email_enabled: boolean;
  url: string | null;
}

export interface TestProjectWebhookInput {
  url?: string;
}

export interface TestProjectWebhookResult {
  status: "success" | "failed" | string;
  status_code?: number | null;
  error?: string | null;
}

export interface UpdateProjectProtectInput {
  protect_enabled: boolean;
  protect_fail_mode: "open" | "closed";
  apply_clamp: boolean;
  protect_max_req_per_min: number | null;
  protect_max_tok_per_min: number | null;
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
  user: AuthUser;
}

export interface FeedbackInput {
  report_type?: "feedback" | "bug";
  message: string;
  email?: string | null;
  screenshot_name?: string | null;
  screenshot_content_type?: string | null;
  screenshot_base64?: string | null;
  project_id?: string | null;
  page?: string | null;
  mode?: string | null;
  timestamp?: string | null;
  app_version?: string | null;
}

export interface PublicConfigResponse {
  public_contact_email: string;
}

export interface ApiVersionResponse {
  version: string;
  environment: string;
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
let refreshInFlight: Promise<boolean> | null = null;
let lastRefreshSucceededAtMs = 0;
const recentRefreshRetryWindowMs = 1500;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

export function resetClientAuthStateForTests(): void {
  unauthorizedHandler = null;
  refreshInFlight = null;
  lastRefreshSucceededAtMs = 0;
}

async function executeRequest(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers ?? {});
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return await fetch(`${frontendConfig.apiBaseUrl}${path}`, {
    headers,
    credentials: "include",
    ...init,
  });
}

async function executeRequestWithRefreshBarrier(
  path: string,
  init: RequestInit | undefined,
  *,
  isAuthRoute: boolean,
): Promise<Response> {
  // If another request is already refreshing the cookie session, wait for it
  // so protected dashboard/API calls do not race into avoidable 401 responses.
  if (!isAuthRoute && refreshInFlight) {
    await refreshInFlight;
  }
  return await executeRequest(path, init);
}

async function parseApiError(response: Response): Promise<ApiError> {
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
  return new ApiError(response.status, responseMessage, responseCode);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isAuthRoute = path.startsWith("/api/v1/auth/");
  const allowsRefreshRetry = !isAuthRoute || path === "/api/v1/auth/me";
  const response = await executeRequestWithRefreshBarrier(path, init, { isAuthRoute });

  if (response.status === 401) {
    if (allowsRefreshRetry) {
      if (Date.now() - lastRefreshSucceededAtMs <= recentRefreshRetryWindowMs) {
        const recentRetryResponse = await executeRequestWithRefreshBarrier(path, init, { isAuthRoute });
        if (recentRetryResponse.ok) {
          return (await recentRetryResponse.json()) as T;
        }
        if (recentRetryResponse.status !== 401) {
          throw await parseApiError(recentRetryResponse);
        }
      }
      const refreshed = await refreshSession();
      if (refreshed) {
        const retryResponse = await executeRequestWithRefreshBarrier(path, init, { isAuthRoute });
        if (retryResponse.ok) {
          return (await retryResponse.json()) as T;
        }
        if (retryResponse.status !== 401) {
          throw await parseApiError(retryResponse);
        }
      }
    }
    unauthorizedHandler?.();
    throw await parseApiError(response);
  }

  if (!response.ok) {
    throw await parseApiError(response);
  }

  return (await response.json()) as T;
}

async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) {
    return refreshInFlight;
  }
  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${frontendConfig.apiBaseUrl}/api/v1/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
      });
      if (response.ok) {
        lastRefreshSucceededAtMs = Date.now();
      }
      return response.ok;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
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

export async function fetchCurrentUser(): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/me");
}

export async function logout(): Promise<{ status: string }> {
  const response = await fetch(`${frontendConfig.apiBaseUrl}/api/v1/auth/logout`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
  });
  if (response.status === 401) {
    return { status: "ok" };
  }
  if (!response.ok) {
    throw new ApiError(response.status, `Request failed: ${response.status}`);
  }
  return (await response.json()) as { status: string };
}

export async function fetchMetrics(projectId: string, provider?: string): Promise<RealtimeMetrics> {
  const providerQuery = provider ? `&provider=${encodeURIComponent(provider)}` : "";
  return request<RealtimeMetrics>(`/api/v1/metrics/realtime?project_id=${encodeURIComponent(projectId)}${providerQuery}`);
}

export async function fetchProtectMetrics(projectId: string, provider?: string): Promise<ProtectMetrics> {
  const providerQuery = provider ? `&provider=${encodeURIComponent(provider)}` : "";
  return request<ProtectMetrics>(`/api/v1/metrics/protect?project_id=${encodeURIComponent(projectId)}${providerQuery}`);
}

export async function fetchProtectHealth(projectId: string, provider?: string): Promise<ProtectHealthMetrics> {
  const providerQuery = provider ? `&provider=${encodeURIComponent(provider)}` : "";
  return request<ProtectHealthMetrics>(`/api/v1/metrics/protect/health?project_id=${encodeURIComponent(projectId)}${providerQuery}`);
}

export async function fetchDeliveryFailures(
  projectId: string,
  kind: "webhook" | "email" = "webhook",
): Promise<DeliveryFailures> {
  return request<DeliveryFailures>(
    `/api/v1/metrics/delivery-failures?project_id=${encodeURIComponent(projectId)}&kind=${encodeURIComponent(kind)}`,
  );
}

export async function fetchProjectProtect(projectId: string): Promise<ProjectProtectSettings> {
  return request<ProjectProtectSettings>(`/api/v1/projects/${encodeURIComponent(projectId)}/protect`);
}

export async function updateProjectProtect(
  projectId: string,
  payload: UpdateProjectProtectInput,
): Promise<ProjectProtectSettings> {
  return request<ProjectProtectSettings>(`/api/v1/projects/${encodeURIComponent(projectId)}/protect`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function fetchProjectWebhook(projectId: string): Promise<ProjectWebhookSettings> {
  return request<ProjectWebhookSettings>(`/api/v1/projects/${encodeURIComponent(projectId)}/webhook`);
}

export async function updateProjectWebhook(
  projectId: string,
  payload: UpdateProjectWebhookInput,
): Promise<ProjectWebhookSettings> {
  return request<ProjectWebhookSettings>(`/api/v1/projects/${encodeURIComponent(projectId)}/webhook`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function testProjectWebhook(projectId: string, payload?: TestProjectWebhookInput): Promise<TestProjectWebhookResult> {
  return request<TestProjectWebhookResult>(`/api/v1/projects/${encodeURIComponent(projectId)}/webhook/test`, {
    method: "POST",
    body: payload ? JSON.stringify(payload) : undefined,
  });
}

export async function fetchIncidents(
  projectId: string,
  provider?: string,
  status?: "open" | "resolved" | "all",
): Promise<IncidentItem[]> {
  const providerQuery = provider ? `&provider=${encodeURIComponent(provider)}` : "";
  const statusQuery = status ? `&status=${encodeURIComponent(status)}` : "";
  return request<IncidentItem[]>(`/api/v1/incidents?project_id=${encodeURIComponent(projectId)}${providerQuery}${statusQuery}`);
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

export async function fetchProjectProviders(projectId: string): Promise<string[]> {
  const response = await request<ProjectProvidersResponse>(`/api/v1/projects/${encodeURIComponent(projectId)}/providers`);
  return response.providers;
}

export async function createProject(name: string): Promise<ProjectItem> {
  return request<ProjectItem>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function deleteProject(projectId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
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

export async function sendFeedback(payload: FeedbackInput): Promise<{ status: string }> {
  return request<{ status: string }>("/api/v1/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchPublicConfig(): Promise<PublicConfigResponse> {
  return request<PublicConfigResponse>("/api/v1/public-config");
}

export async function fetchApiVersion(): Promise<ApiVersionResponse> {
  return request<ApiVersionResponse>("/api/v1/version");
}
