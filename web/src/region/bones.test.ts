import { describe, expect, it } from "vitest";
import { GRAPH } from "../config";
import { REGION, SIDE } from "@gen/types";
import { bodyPasses, bodyPlacements } from "./bones";
import { everything } from "./groups";

const places = bodyPlacements(GRAPH.nodes);
const only = (regions: string[], sides: string[] = [...SIDE]) =>
  ({ regions: new Set(REGION.filter((r) => regions.includes(r))), sides: new Set(SIDE.filter((s) => sides.includes(s))) });

describe("bone filter by region", () => {
  it("maps bodies to the regions of their bone nodes", () => {
    expect(places.get("femur_r")).toEqual([{ region: "lowerLimb", side: "right" }]);
    expect(places.get("head")?.every((p) => p.region === "head")).toBe(true);
    expect(places.get("torso")?.some((p) => p.side === "left")).toBe(true);
    expect(places.get("torso")?.some((p) => p.side === "right")).toBe(true);
  });

  it("keeps every body under the full selection", () => {
    for (const body of places.keys()) expect(bodyPasses(everything(), places.get(body))).toBe(true);
  });

  it("hides a body when its region leaves the selection", () => {
    const sel = only(["trunk", "pelvis", "head", "upperLimb"]);
    expect(bodyPasses(sel, places.get("femur_r"))).toBe(false);
    expect(bodyPasses(sel, places.get("torso"))).toBe(true);
    expect(bodyPasses(only(["lowerLimb"]), places.get("head"))).toBe(false);
  });

  it("hides a body when its side leaves the selection", () => {
    const rightOnly = only([...REGION], ["right", "midline"]);
    expect(bodyPasses(rightOnly, places.get("femur_l"))).toBe(false);
    expect(bodyPasses(rightOnly, places.get("femur_r"))).toBe(true);
    expect(bodyPasses(rightOnly, places.get("torso"))).toBe(true);
  });

  it("shows a body that no bone node names", () => {
    expect(bodyPasses(only([]), places.get("lumbar_unknown"))).toBe(true);
  });
});
