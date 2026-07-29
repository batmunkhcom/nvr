import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, vi } from "vitest";

beforeAll(() => {
  // LazyMiniPreview uses IntersectionObserver; jsdom does not provide it.
  // Fire the callback immediately so tests see the preview.
  globalThis.IntersectionObserver = class {
    callback: IntersectionObserverCallback;
    root: Element | null = null;
    rootMargin = "0px";
    thresholds = [0];
    observe = vi.fn((target: Element) => {
      if (this.callback) {
        this.callback([{ isIntersecting: true, target } as IntersectionObserverEntry], this);
      }
    });
    disconnect = vi.fn();
    unobserve = vi.fn();
    takeRecords = vi.fn(() => []);
    constructor(callback: IntersectionObserverCallback) {
      this.callback = callback;
    }
  } as unknown as typeof IntersectionObserver;
});

afterEach(() => {
  cleanup();
});
