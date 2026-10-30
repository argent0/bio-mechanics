import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { findStride, frameAt, parseMusclePaths } from "./clip";

const raw = JSON.parse(readFileSync(new URL("../../../data/out/muscle_paths.json", import.meta.url), "utf8"));

describe("bm-muscle-paths/1", () => {
  const clip = parseMusclePaths(raw);

  it("parses the real file: 119 frames at 50 Hz, 13 bodies, 80 muscles", () => {
    expect(clip.rateHz).toBe(50);
    expect(clip.time.length).toBe(119);
    expect(clip.time[118]).toBeCloseTo(2.36, 6);
    expect([...clip.bodies.keys()]).toHaveLength(13);
    expect(clip.bodies.get("pelvis")).toHaveLength(119 * 7);
    expect(clip.muscles.size).toBe(80);
  });

  it("keeps per-frame point lists whole (3 numbers per point, at least two points)", () => {
    for (const m of clip.muscles.values()) {
      expect(m.activation).toHaveLength(119);
      expect(m.velocity).toHaveLength(119);
      for (const p of m.points) {
        expect(p.length % 3).toBe(0);
        expect(p.length).toBeGreaterThanOrEqual(6);
      }
    }
  });

  it("names the offending field on a bad file", () => {
    expect(() => parseMusclePaths({ ...raw, format: "bm-muscle-paths/2" })).toThrow(/format/);
    expect(() => parseMusclePaths({ ...raw, time: [0] })).toThrow(/time/);
    expect(() => parseMusclePaths({ ...raw, bodies: { pelvis: [[0, 0, 0]] } })).toThrow(/bodies.pelvis/);
  });

  it("finds the stride the pipeline reports (0.27-1.42 s) within one frame", () => {
    const s = findStride(clip);
    expect(Math.abs(s.start - 0.27)).toBeLessThan(0.03);
    expect(Math.abs(s.end - 1.42)).toBeLessThan(0.03);
  });

  it("prefers a stride the file carries", () => {
    expect(findStride(parseMusclePaths({ ...raw, stride: { start: 0.27, end: 1.42 } }))).toEqual({ start: 0.27, end: 1.42 });
  });
});

describe("frameAt", () => {
  const time = [0, 0.02, 0.04];
  it("weights the two frames around t and clamps outside", () => {
    expect(frameAt(time, 0.03)).toEqual({ i0: 1, i1: 2, f: expect.closeTo(0.5, 9) });
    expect(frameAt(time, -1)).toEqual({ i0: 0, i1: 0, f: 0 });
    expect(frameAt(time, 9)).toEqual({ i0: 2, i1: 2, f: 0 });
    expect(frameAt(time, 0.02)).toEqual({ i0: 1, i1: 2, f: 0 });
  });
});
