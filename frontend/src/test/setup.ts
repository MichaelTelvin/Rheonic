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

Object.defineProperty(window, "sessionStorage", {
  value: createStorage(),
  configurable: true,
});

class MockIntersectionObserver {
  public root: Element | Document | null = null;
  public rootMargin = "0px";
  public thresholds: ReadonlyArray<number> = [];

  public observe(): void {}
  public unobserve(): void {}
  public disconnect(): void {}
  public takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

Object.defineProperty(window, "IntersectionObserver", {
  value: MockIntersectionObserver,
  configurable: true,
});

Object.defineProperty(globalThis, "IntersectionObserver", {
  value: MockIntersectionObserver,
  configurable: true,
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
});
