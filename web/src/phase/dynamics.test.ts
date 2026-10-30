import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Graph } from "@gen/types";
import { GRAPH } from "../config";
import { GraphStore } from "../store/GraphStore";
import { QueryEngine } from "../query/QueryEngine";
import { findStride, parseMusclePaths } from "../timeline/clip";
import { FORMAT, momentScale, parseDynamics, tugOfWarAt } from "./dynamics";
import { sequenceModel } from "./sequence";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const raw = read("../../../data/out/dynamics.json");
const dyn = parseDynamics(raw);
const clip = parseMusclePaths(read("../../../data/out/muscle_paths.json"));
const stride = findStride(clip);
const fixture = new QueryEngine(new GraphStore(read("../../../data/fixtures/graph.sample.json") as Graph));
const real = new QueryEngine(new GraphStore(GRAPH));

describe("parseDynamics", () => {
  it("reads the pipeline's file on the clip's frames", () => {
    expect(Array.from(dyn.time)).toEqual(Array.from(clip.time));
    expect(dyn.coordinates.map((c) => c.coordinate)).toEqual(["hip_flexion_r", "hip_adduction_r", "hip_rotation_r", "knee_angle_r", "ankle_angle_r"]);
    const knee = dyn.coordinates[3]!;
    expect([knee.joint, knee.positive, knee.negative]).toEqual(["joint:knee_r", "action:knee_flexion_r", "action:knee_extension_r"]);
    for (const id of [knee.joint, knee.positive, knee.negative, ...knee.moments.keys()]) expect(real.node(id)).toBeDefined();
  });

  it("rejects a wrong format and a short series", () => {
    expect(() => parseDynamics({ ...raw, format: "x" })).toThrow(FORMAT);
    const bad = structuredClone(raw);
    bad.coordinates[0].angleDeg.pop();
    expect(() => parseDynamics(bad)).toThrow("angleDeg");
  });
});

describe("tugOfWarAt", () => {
  const mid = stride.start + 0.27 * (stride.end - stride.start);
  const bars = tugOfWarAt(dyn, clip, mid);

  it("splits each coordinate's muscles by the sign of their moment, largest first, and sums the net", () => {
    for (const b of bars) {
      expect(b.pushPositive.every((s) => s.moment > 0)).toBe(true);
      expect(b.pushNegative.every((s) => s.moment < 0)).toBe(true);
      expect(b.pushPositive.map((s) => s.moment)).toEqual([...b.pushPositive.map((s) => s.moment)].sort((x, y) => y - x));
      const sum = [...b.pushPositive, ...b.pushNegative].reduce((s, x) => s + x.moment, 0);
      expect(b.net).toBeCloseTo(sum, 6);
    }
  });

  it("in single-leg support the hip muscles push toward abduction, led by gluteus medius", () => {
    const hip = bars.find((b) => b.coordinate === "hip_adduction_r")!;
    expect(hip.net).toBeLessThan(0);
    expect(hip.pushNegative[0]!.muscle).toBe("muscle:glmed1_r");
  });

  it("gives each frame of the stride a scale at least as wide as its largest push", () => {
    const scales = momentScale(dyn, stride);
    for (const b of bars) {
      const s = scales.get(b.coordinate)!;
      expect(b.pushPositive.reduce((x, m) => x + m.moment, 0)).toBeLessThanOrEqual(s + 1e-9);
      expect(-b.pushNegative.reduce((x, m) => x + m.moment, 0)).toBeLessThanOrEqual(s + 1e-9);
    }
  });
});

describe("sequenceModel", () => {
  it("lists each muscle of the phase once, with peak and onset (fixture)", () => {
    const rows = sequenceModel(fixture, "phase:loadingResponse");
    expect(rows.map((r) => r.id)).toEqual([
      "muscle:vaslat_r", "muscle:glmax1_r", "muscle:ercspn_r", "muscle:ercspn_l", "muscle:bflh_r", "muscle:bflh_l",
    ]);
    expect(rows[0]).toMatchObject({ peak: 0.45, peakAt: 0.5, onsetAt: 0.2, commonName: "outer quad" });
  });

  it("orders single-leg support from the early big glute to the late calf (pipeline graph)", () => {
    const ids = sequenceModel(real, "phase:midStance").map((r) => r.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.indexOf("muscle:glmax2_r")).toBeLessThan(ids.indexOf("muscle:gasmed_r"));
  });
});
