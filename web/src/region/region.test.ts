import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { REGION, type Graph, type Region, type Side } from "@gen/types";
import { RegionFilter } from "./RegionFilter";
import { everything, filterNodes, groupByRegionSide, groupHeading, passes } from "./groups";

const fixture = JSON.parse(readFileSync(new URL("../../../data/fixtures/graph.sample.json", import.meta.url), "utf8")) as Graph;
const nodes = fixture.nodes;
const sel = (regions: Region[], sides: Side[]) => ({ regions: new Set(regions), sides: new Set(sides) });
const ids = (ns: { id: string }[]) => ns.map((n) => n.id);

describe("passes and filterNodes (fixture graph)", () => {
  it("keeps every node under the full selection", () => {
    expect(filterNodes(everything(), nodes)).toHaveLength(nodes.length);
  });

  it("keeps the regions and sides selected, and every node without a region", () => {
    const out = filterNodes(sel(["trunk"], ["right", "left", "midline"]), nodes);
    const regional = out.filter((n) => n.region !== null);
    expect(regional.length).toBeGreaterThan(0);
    expect(regional.every((n) => n.region === "trunk")).toBe(true);
    expect(ids(out)).toContain("phase:loadingResponse");
    expect(ids(out)).toContain("muscle:ercspn_l");
    expect(ids(out)).not.toContain("muscle:glmax1_r");
  });

  it("crosses regions with sides: left knee only", () => {
    const out = filterNodes(sel(["lowerLimb"], ["left"]), nodes).filter((n) => n.region !== null);
    expect(out.length).toBeGreaterThan(0);
    expect(out.every((n) => n.region === "lowerLimb" && n.side === "left")).toBe(true);
    expect(ids(out)).toContain("joint:knee_l");
    expect(ids(out)).not.toContain("joint:knee_r");
  });

  it("keeps only the regionless nodes under the empty selection", () => {
    const out = filterNodes(sel([], []), nodes);
    expect(out.every((n) => n.region === null)).toBe(true);
    expect(out.length).toBeGreaterThan(0);
  });

  it("passes a node with no region on any side", () => {
    expect(passes(sel([], []), { region: null, side: "midline" })).toBe(true);
  });
});

describe("RegionFilter", () => {
  it("starts with everything and tells listeners about each change", () => {
    const f = new RegionFilter();
    expect(f.isEverything).toBe(true);
    let calls = 0;
    const off = f.onChange(() => calls++);
    f.setRegion("head", false);
    f.setRegion("head", false);
    f.setSide("left", false);
    expect(calls).toBe(2);
    expect(f.hasRegion("head")).toBe(false);
    expect(f.passes({ region: "trunk", side: "left" })).toBe(false);
    expect(f.passes({ region: "trunk", side: "right" })).toBe(true);
    off();
    f.reset();
    expect(calls).toBe(2);
    expect(f.isEverything).toBe(true);
  });
});

describe("groupByRegionSide", () => {
  it("orders groups by REGION, then right, left, midline, and leaves empty groups out", () => {
    const groups = groupByRegionSide(nodes.filter((n) => n.kind === "muscle"), (n) => n);
    const keys = groups.map((g) => `${g.region}/${g.side}`);
    expect(keys).toEqual(["lowerLimb/right", "lowerLimb/left", "trunk/right", "trunk/left", "upperLimb/right"]);
    const regionRank = groups.map((g) => REGION.indexOf(g.region as Region));
    expect([...regionRank].sort((a, b) => a - b)).toEqual(regionRank);
    expect(groups[0]!.heading).toBe("Lower limb, right");
    expect(ids(groups[3]!.items)).toEqual(["muscle:ercspn_l"]);
  });

  it("closes the list with the items that have no region", () => {
    const groups = groupByRegionSide(nodes.filter((n) => n.kind === "phase" || n.kind === "bone"), (n) => n);
    expect(groups[groups.length - 1]).toMatchObject({ region: null, heading: groupHeading(null, "midline") });
  });
});
