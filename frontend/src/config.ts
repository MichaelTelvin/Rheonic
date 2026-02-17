export const frontendConfig = {
  apiBaseUrl: import.meta.env.DEV ? "" : (import.meta.env.VITE_API_BASE_URL ?? ""),
  dashboardSelectedProjectStorageKey: "selected_project_id",
  dashboardMaxSeriesPoints: 60,
} as const;
