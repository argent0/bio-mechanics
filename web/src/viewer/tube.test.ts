import { describe, expect, it } from "vitest";
import { RADIAL, RINGS, resamplePath, tubeIndices, writeTube } from "./tube";

describe("resamplePath", () => {
  it("spaces RINGS points evenly along a bent path and keeps its ends", () => {
    const path = [0, 0, 0, 1, 0, 0, 1, 1, 0]; // length 2
    const out = resamplePath(path, new Float32Array(RINGS * 3));
    expect([...out.slice(0, 3)]).toEqual([0, 0, 0]);
    expect([...out.slice(-3)]).toEqual([1, 1, 0]);
    const step = 2 / (RINGS - 1);
    for (let i = 1; i < RINGS; i++) {
      const [ax, ay] = [out[(i - 1) * 3]!, out[(i - 1) * 3 + 1]!];
      const [bx, by] = [out[i * 3]!, out[i * 3 + 1]!];
      // Arc length between neighbours equals the step unless the corner lies between them.
      expect(Math.hypot(bx - ax, by - ay)).toBeLessThanOrEqual(step + 1e-6);
    }
  });
  it("handles a zero-length path without NaN", () => {
    const out = resamplePath([1, 2, 3, 1, 2, 3], new Float32Array(RINGS * 3));
    expect(out.every(Number.isFinite)).toBe(true);
  });
});

describe("writeTube", () => {
  const centre = new Float32Array(RINGS * 3);
  for (let i = 0; i < RINGS; i++) centre.set([i * 0.02, 0.5, 0], i * 3);
  const positions = new Float32Array(RINGS * RADIAL * 3);
  const normals = new Float32Array(RINGS * RADIAL * 3);
  writeTube(centre, 0.01, positions, normals);

  it("puts every vertex one spindle radius from the centreline, normals unit and radial", () => {
    for (let i = 0; i < RINGS; i++) {
      const r = 0.01 * (0.55 + 0.45 * Math.sin((Math.PI * i) / (RINGS - 1)));
      for (let j = 0; j < RADIAL; j++) {
        const o = (i * RADIAL + j) * 3;
        const d = Math.hypot(positions[o]! - centre[i * 3]!, positions[o + 1]! - centre[i * 3 + 1]!, positions[o + 2]! - centre[i * 3 + 2]!);
        expect(d).toBeCloseTo(r, 6);
        expect(Math.hypot(normals[o]!, normals[o + 1]!, normals[o + 2]!)).toBeCloseTo(1, 6);
        expect(normals[o]!).toBeCloseTo(0, 6); // radial to a path along x
      }
    }
  });
  it("indexes only existing vertices", () => {
    const idx = tubeIndices();
    expect(Math.max(...idx)).toBe(RINGS * RADIAL - 1);
    expect(idx.length).toBe((RINGS - 1) * RADIAL * 6);
  });
  it("rewrites a whole real-sized tube within a millisecond", () => {
    const t0 = performance.now();
    for (let k = 0; k < 80 * 10; k++) writeTube(centre, 0.006, positions, normals);
    expect((performance.now() - t0) / 10).toBeLessThan(16);
  });
});
