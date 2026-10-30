import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Graph } from "@gen/types";
import { RegionFilter } from "../region";
import { placeLabel, searchNodes, searchOptions } from "./search";

const nodes = (JSON.parse(readFileSync(new URL("../../../data/fixtures/graph.sample.json", import.meta.url), "utf8")) as Graph).nodes;
const ids = (ns: { id: string }[]) => ns.map((n) => n.id);

describe("searchNodes (fixture graph, every region)", () => {
  it("finds a name in the legs, the trunk and the arm", () => {
    expect(ids(searchNodes(nodes, "erector")).sort()).toEqual(["muscle:ercspn_l", "muscle:ercspn_r"]);
    expect(ids(searchNodes(nodes, "biceps"))).toEqual(expect.arrayContaining(["muscle:biclong_r", "muscle:bflh_r"]));
    expect(ids(searchNodes(nodes, "deltoid"))).toEqual(["muscle:delt3_r"]);
  });

  it("finds both knees for 'knee' and the left one for 'left knee'", () => {
    expect(ids(searchNodes(nodes, "knee")).filter((i) => i.startsWith("joint:"))).toEqual(["joint:knee_r", "joint:knee_l"]);
    expect(ids(searchNodes(nodes, "left knee")).filter((i) => i.startsWith("joint:"))).toEqual(["joint:knee_l"]);
  });

  it("matches region names", () => {
    const hits = searchNodes(nodes, "upper limb muscle");
    expect(ids(hits).sort()).toEqual(["muscle:biclong_r", "muscle:delt3_r", "muscle:trilong_r"]);
    expect(searchNodes(nodes, "trunk").every((n) => n.region === "trunk" || n.name.includes("trunk"))).toBe(true);
  });

  it("ranks an exact name first and answers nothing for empty text", () => {
    expect(searchNodes(nodes, "knee joint")[0]?.kind).toBe("joint");
    expect(searchNodes(nodes, "  ")).toEqual([]);
  });

  it("leaves out nodes the region filter hides", () => {
    const f = new RegionFilter();
    f.setSide("left", false);
    expect(ids(searchNodes(nodes, "erector", (n) => f.passes(n)))).toEqual(["muscle:ercspn_r"]);
  });
});

describe("searchOptions", () => {
  it("names the place so left and right differ, and each option finds its own node", () => {
    const opts = searchOptions(nodes);
    const erector = opts.filter((o) => o.node.id.startsWith("muscle:ercspn"));
    expect(erector.map((o) => o.value).sort()).toEqual(["back extensors · Trunk, left", "back extensors · Trunk, right"]);
    for (const o of opts) expect(ids(searchNodes(nodes, o.value))).toContain(o.node.id);
  });

  it("labels a phase as whole body", () => {
    expect(placeLabel({ region: null, side: "midline" })).toBe("Whole body");
  });
});
