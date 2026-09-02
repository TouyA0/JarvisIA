import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useIsMobile } from "./useIsMobile";

function mockMatchMedia(initialMatches) {
  const listeners = new Set();
  const state = { matches: initialMatches };
  window.matchMedia = (query) => ({
    get matches() {
      return state.matches;
    },
    media: query,
    addEventListener: (_, cb) => listeners.add(cb),
    removeEventListener: (_, cb) => listeners.delete(cb),
  });
  return {
    setMatches: (value) => {
      state.matches = value;
      listeners.forEach((cb) => cb());
    },
  };
}

describe("useIsMobile", () => {
  beforeEach(() => {
    window.innerWidth = 1024;
  });

  it("renvoie false au-dessus du point de rupture", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
  });

  it("renvoie true sous le point de rupture", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it("réagit à un changement de largeur via l'écouteur matchMedia", () => {
    const mm = mockMatchMedia(false);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);

    act(() => {
      mm.setMatches(true);
    });
    expect(result.current).toBe(true);
  });
});
