import { describe, expect, it } from "vitest";
import { GRAPH } from "../config";
import { NECK_ASSUMPTION_NOTE, neckAssumption } from "./assumption";
import { assumedBadge } from "../phase/PhasePanel";

describe("head-level assumption label (D-010)", () => {
  const nodes = GRAPH.nodes;

  it("marks every neck muscle and neck joint action", () => {
    const neck = nodes.filter((n) => n.region === "head" && (n.kind === "muscle" || n.kind === "jointAction"));
    expect(neck.length).toBeGreaterThan(0);
    for (const n of neck) expect(neckAssumption(n)).toBe(NECK_ASSUMPTION_NOTE);
  });

  it("leaves every other node unmarked", () => {
    for (const n of nodes.filter((n) => !(n.region === "head" && (n.kind === "muscle" || n.kind === "jointAction")))) {
      expect(neckAssumption(n)).toBeNull();
    }
  });

  it("names the head held level in space", () => {
    expect(NECK_ASSUMPTION_NOTE).toContain("D-010");
    expect(NECK_ASSUMPTION_NOTE).toContain("level in space");
  });

  it("renders a badge in the phase panel only for a note", () => {
    expect(assumedBadge(null)).toBe("");
    expect(assumedBadge(NECK_ASSUMPTION_NOTE)).toContain('data-assumption="head-level"');
    expect(assumedBadge(NECK_ASSUMPTION_NOTE)).toContain("D-010");
  });
});
