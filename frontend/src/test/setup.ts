import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

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

Object.defineProperty(window, "scrollTo", {
  value: () => {},
  configurable: true,
});

const mockCanvasContext = {
  clearRect: () => {},
  setTransform: () => {},
  save: () => {},
  restore: () => {},
  beginPath: () => {},
  moveTo: () => {},
  lineTo: () => {},
  stroke: () => {},
  fill: () => {},
  closePath: () => {},
  quadraticCurveTo: () => {},
  setLineDash: () => {},
  strokeStyle: "",
  lineWidth: 1,
  fillStyle: "",
  shadowColor: "",
  shadowBlur: 0,
  globalAlpha: 1,
};

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  value: () => mockCanvasContext,
  configurable: true,
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
});
