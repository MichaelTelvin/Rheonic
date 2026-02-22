import { frontendConfig } from "./config";

function migrateLegacyAuthStorage(): void {
  const keys = [
    frontendConfig.authTokenStorageKey,
    frontendConfig.authRefreshTokenStorageKey,
    frontendConfig.authUserStorageKey,
  ];
  for (const key of keys) {
    if (window.sessionStorage.getItem(key) !== null) {
      continue;
    }
    const legacyValue = window.localStorage.getItem(key);
    if (legacyValue !== null) {
      window.sessionStorage.setItem(key, legacyValue);
      window.localStorage.removeItem(key);
    }
  }
}

export function getAuthItem(key: string): string | null {
  migrateLegacyAuthStorage();
  return window.sessionStorage.getItem(key);
}

export function setAuthItem(key: string, value: string): void {
  window.sessionStorage.setItem(key, value);
  window.localStorage.removeItem(key);
}

export function removeAuthItem(key: string): void {
  window.sessionStorage.removeItem(key);
  window.localStorage.removeItem(key);
}
