import { describe, expect, it } from "vitest";
import { A_ACTIVE, HUE, L_MAX, L_MIN, OPACITY_MIN, V_ISOMETRIC, hslToRgb, muscleColour, workType } from "./colour";

describe("work type", () => {
  it("is eccentric when lengthening while active, concentric when shortening", () => {
    expect(workType(0.5, 0.2)).toBe("eccentric");
    expect(workType(0.5, -0.2)).toBe("concentric");
  });
  it("is isometric at the speed threshold and within it", () => {
    expect(workType(0.5, V_ISOMETRIC)).toBe("isometric");
    expect(workType(0.5, -V_ISOMETRIC)).toBe("isometric");
    expect(workType(0.5, 0)).toBe("isometric");
    expect(workType(0.5, V_ISOMETRIC + 1e-6)).toBe("eccentric");
  });
  it("is isometric (resting) below the activation threshold whatever the velocity", () => {
    expect(workType(A_ACTIVE - 1e-6, 1)).toBe("isometric");
    expect(workType(A_ACTIVE, 1)).toBe("eccentric");
  });
});

describe("muscle colour", () => {
  it("activation 0 is dark and faint, activation 1 bright and solid", () => {
    const lo = muscleColour(0, 0.3);
    const hi = muscleColour(1, 0.3);
    expect(lo).toMatchObject({ l: L_MIN, opacity: OPACITY_MIN, work: "isometric" });
    expect(hi).toMatchObject({ l: L_MAX, opacity: 1, work: "eccentric", h: HUE.eccentric });
  });
  it("clamps activation outside 0-1", () => {
    expect(muscleColour(-3, 0).l).toBe(L_MIN);
    expect(muscleColour(7, 0).opacity).toBe(1);
  });
  it("increases lightness and opacity with activation", () => {
    const a = muscleColour(0.3, -0.1);
    const b = muscleColour(0.6, -0.1);
    expect(b.l).toBeGreaterThan(a.l);
    expect(b.opacity).toBeGreaterThan(a.opacity);
    expect(a.h).toBe(HUE.concentric);
  });
  it("keeps the three work types at distinct hues", () => {
    expect(new Set(Object.values(HUE)).size).toBe(3);
  });
});

describe("hslToRgb", () => {
  it("maps primaries and greys", () => {
    expect(hslToRgb(0, 1, 0.5)).toEqual([1, 0, 0]);
    expect(hslToRgb(120, 1, 0.5)[1]).toBe(1);
    expect(hslToRgb(240, 1, 0.5)[2]).toBe(1);
    expect(hslToRgb(77, 0, 0.4)).toEqual([0.4, 0.4, 0.4]);
  });
});
