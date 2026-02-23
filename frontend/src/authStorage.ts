import { frontendConfig } from "./config";

function migrateLegacyAuthStorage(): void {
  const keys = [
    frontendConfig.authTokenStorageKey,
    frontendConfig.authRefreshTokenStorageKey,
    frontendConfig.authUserStorageKey,
  ];
  for (const key of keys) {
    const sessionValue = window.sessionStorage.getItem(key);
    const localValue = window.localStorage.getItem(key);

    if (sessionValue !== null && localValue === null) {
      window.localStorage.setItem(key, sessionValue);
      continue;
    }

    if (sessionValue === null && localValue !== null) {
      window.sessionStorage.setItem(key, localValue);
    }
  }
}

export function getAuthItem(key: string): string | null {
  migrateLegacyAuthStorage();
  return window.sessionStorage.getItem(key) ?? window.localStorage.getItem(key);
}

export function setAuthItem(key: string, value: string): void {
  window.sessionStorage.setItem(key, value);
  window.localStorage.setItem(key, value);
}

export function removeAuthItem(key: string): void {
  window.sessionStorage.removeItem(key);
  window.localStorage.removeItem(key);
}
