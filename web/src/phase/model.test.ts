import { describe, expect, it } from "vitest";
import { GRAPH } from "../config";
import { GraphStore } from "../store/GraphStore";
import { QueryEngine } from "../query/QueryEngine";
import { phasePanelModel } from "./model";
import { sparkline } from "./PhasePanel";

const query = new QueryEngine(new GraphStore(GRAPH));

describe("phasePanelModel", () => {
  const loading = phasePanelModel(query, "phase:loadingResponse")!;

  it("names the phase in plain and formal terms", () => {
    expect(loading).toMatchObject({ id: "phase:loadingResponse", name: "loading response", commonName: "weight acceptance" });
  });

  it("loading response: knee flexion with vastus lateralis as a braking antagonist", () => {
    const knee = loading.actions.find((a) => a.id === "action:knee_flexion_r")!;
    expect(knee).toBeDefined();
    expect(knee.commonName).toBe("bending the knee");
    const vl = knee.muscles.find((m) => m.id === "muscle:vaslat_r")!;
    expect(vl).toMatchObject({
      name: "vastus lateralis",
      commonName: "outer quad",
      role: "antagonist",
      roleLabel: "antagonist",
      contraction: "eccentric",
      workLabel: "braking",
    });
    expect(vl.activation.length).toBeGreaterThan(1);
  });

  it("lists main movers before helpers before antagonists, strongest first", () => {
    for (const a of loading.actions) {
      const order = ["mainMover", "helper", "stabiliser", "antagonist"];
      const ranks = a.muscles.map((m) => order.indexOf(m.role));
      expect(ranks).toEqual([...ranks].sort((x, y) => x - y));
    }
  });

  it("matches the graph: every drivenBy edge of the phase appears once", () => {
    const edges = query.edgesOf("drivenBy").filter((e) => e.phase === "phase:loadingResponse");
    const rows = loading.actions.flatMap((a) => a.muscles);
    expect(rows).toHaveLength(edges.length);
  });

  it("covers all seven phases and is undefined for an unknown id", () => {
    for (const p of ["loadingResponse", "midStance", "terminalStance", "preSwing", "initialSwing", "midSwing", "terminalSwing"]) {
      expect(phasePanelModel(query, `phase:${p}`)?.actions.length).toBeGreaterThan(0);
    }
    expect(phasePanelModel(query, "phase:nope")).toBeUndefined();
  });
});

describe("sparkline", () => {
  it("draws one point per sample, with 1 at the top and 0 at the baseline", () => {
    const svg = sparkline([0, 1, 0]);
    const pts = /points="([^"]+)"/.exec(svg)![1]!.split(" ");
    expect(pts).toHaveLength(3);
    expect(Number(pts[0]!.split(",")[1])).toBeGreaterThan(Number(pts[1]!.split(",")[1]));
  });
});
