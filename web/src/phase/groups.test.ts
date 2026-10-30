import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Graph } from "@gen/types";
import { GraphStore } from "../store/GraphStore";
import { QueryEngine } from "../query/QueryEngine";
import { RegionFilter } from "../region";
import { phasePanelModel } from "./model";
import { sequenceGroups, sequenceModel } from "./sequence";

const fixture = JSON.parse(readFileSync(new URL("../../../data/fixtures/graph.sample.json", import.meta.url), "utf8")) as Graph;
const query = new QueryEngine(new GraphStore(fixture));

describe("PhasePanel groups (fixture graph)", () => {
  const model = phasePanelModel(query, "phase:loadingResponse")!;

  it("groups the actions by region and side under headings, in REGION then right-left-midline order", () => {
    expect(model.groups.map((g) => g.heading)).toEqual(["Lower limb, right", "Lower limb, left", "Trunk, midline"]);
    expect(model.groups[0]!.items.map((a) => a.id)).toEqual(["action:knee_flexion_r", "action:hip_extension_r"]);
    const ranges = model.groups[0]!.items.map((a) => a.rangeDeg);
    expect(ranges).toEqual([...ranges].sort((a, b) => b - a));
    expect(model.groups[1]!.items.map((a) => a.id)).toEqual(["action:knee_flexion_l"]);
    expect(model.groups[2]!.items.map((a) => a.id)).toEqual(["action:lumbar_extension"]);
  });

  it("holds every action once", () => {
    expect(model.groups.flatMap((g) => g.items.map((a) => a.id)).sort()).toEqual(model.actions.map((a) => a.id).sort());
  });

  it("narrows to a selection", () => {
    const f = new RegionFilter();
    f.setSide("right", false);
    const left = phasePanelModel(query, "phase:loadingResponse", f.selection)!;
    expect(left.groups.map((g) => g.heading)).toEqual(["Lower limb, left", "Trunk, midline"]);
    f.setRegion("trunk", false);
    expect(phasePanelModel(query, "phase:loadingResponse", f.selection)!.groups.map((g) => g.heading)).toEqual(["Lower limb, left"]);
  });

  it("groups the upper limb of the mid stance", () => {
    const mid = phasePanelModel(query, "phase:midStance")!;
    expect(mid.groups.map((g) => g.heading)).toEqual(["Lower limb, right", "Upper limb, right"]);
  });
});

describe("Dynamics sequence groups (fixture graph)", () => {
  it("groups the muscles of a phase by region and side, each group in peak order", () => {
    const groups = sequenceGroups(sequenceModel(query, "phase:loadingResponse"));
    expect(groups.map((g) => g.heading)).toEqual(["Lower limb, right", "Lower limb, left", "Trunk, right", "Trunk, left"]);
    for (const g of groups) expect(g.items.map((r) => r.peakAt)).toEqual([...g.items.map((r) => r.peakAt)].sort((a, b) => a - b));
  });

  it("keeps the muscles on the selected side", () => {
    const f = new RegionFilter();
    f.setSide("right", false);
    f.setSide("midline", false);
    const rows = sequenceModel(query, "phase:loadingResponse", f.selection);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((r) => r.side === "left")).toBe(true);
  });
});
