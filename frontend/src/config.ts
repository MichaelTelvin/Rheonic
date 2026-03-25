const rawAppVersion = (import.meta.env.VITE_APP_VERSION ?? "").trim();
const suppressedVersionLabels = new Set([
  "dev",
  "development",
  "test",
  "stage",
  "staging",
  "prod",
  "production",
]);
const normalizedAppVersion = suppressedVersionLabels.has(rawAppVersion.toLowerCase()) ? "" : rawAppVersion;

export const frontendConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
  publicContactEmail: import.meta.env.VITE_PUBLIC_CONTACT_EMAIL ?? "contact@rheonic.dev",
  appVersion: normalizedAppVersion,
  dashboardSelectedProjectStorageKey: "selected_project_id",
  dashboardMaxSeriesPoints: 60,
  dashboardClockTickMs: 1000,
  dashboardProtectStatsPollMs: 2000,
  dashboardMetricsPollMs: 2000,
  dashboardIncidentsPollMs: 5000,
  dashboardNameMaxLength: 80,
  dashboardNamePattern: "^[A-Za-z0-9 _.-]+$",
} as const;
