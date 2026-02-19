import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

function createStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
  };
}

Object.defineProperty(window, "localStorage", {
  value: createStorage(),
  configurable: true,
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
