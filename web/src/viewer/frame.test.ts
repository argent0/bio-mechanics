import { describe, expect, it } from "vitest";
import { fitCamera, unionBounds } from "./frame";

describe("unionBounds", () => {
  it("spans every box, the head and hand boxes included", () => {
    const legs = { min: [-0.2, 0, -0.1], max: [0.3, 0.9, 0.1] } as const;
    const head = { min: [-0.1, 1.5, -0.1], max: [0.1, 1.75, 0.1] } as const;
    const hand = { min: [0.3, 0.7, 0.6], max: [0.4, 0.8, 0.7] } as const;
    expect(unionBounds([legs, head, hand])).toEqual({ min: [-0.2, 0, -0.1], max: [0.4, 1.75, 0.7] });
  });

  it("returns undefined when no box has finite corners", () => {
    expect(unionBounds([])).toBeUndefined();
    expect(unionBounds([{ min: [Infinity, 0, 0], max: [-Infinity, 0, 0] }])).toBeUndefined();
  });
});

describe("fitCamera", () => {
  const body = { min: [-0.3, 0, -0.3], max: [0.3, 1.8, 0.3] } as const;

  it("centres on the bounds and keeps the sphere inside the view", () => {
    const fit = fitCamera(body, 40, 1.5, 1);
    expect(fit.centre).toEqual([0, 0.9, 0]);
    expect(fit.radius).toBeCloseTo(Math.hypot(0.3, 0.9, 0.3), 9);
    // The sphere subtends the vertical half angle exactly at the fitted distance.
    expect(Math.asin(fit.radius / fit.distance)).toBeCloseTo((20 * Math.PI) / 180, 9);
  });

  it("backs off further in a narrow view, where the width limits the fit", () => {
    expect(fitCamera(body, 40, 0.5).distance).toBeGreaterThan(fitCamera(body, 40, 1.5).distance);
  });

  it("grows with the body: a skeleton with raised hands needs more room than the legs alone", () => {
    const legs = { min: [-0.3, 0, -0.3], max: [0.3, 0.9, 0.3] } as const;
    expect(fitCamera(body, 40, 1).distance).toBeGreaterThan(fitCamera(legs, 40, 1).distance);
  });

  it("scales with the margin", () => {
    expect(fitCamera(body, 40, 1, 1.2).distance / fitCamera(body, 40, 1, 1).distance).toBeCloseTo(1.2, 9);
  });
});
