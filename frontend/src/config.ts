export const frontendConfig = {
  apiBaseUrl: import.meta.env.DEV ? "" : (import.meta.env.VITE_API_BASE_URL ?? ""),
  dashboardSelectedProjectStorageKey: "selected_project_id",
  authTokenStorageKey: "llmtbg_token",
  authRefreshTokenStorageKey: "llmtbg_refresh_token",
  authUserStorageKey: "llmtbg_user",
  dashboardMaxSeriesPoints: 60,
} as const;
