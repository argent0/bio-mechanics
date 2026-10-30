import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { CONTRACTION, ROLE, type Graph } from "@gen/types";
import { GRAPH } from "../config";
import { GraphStore } from "../store/GraphStore";
import { QueryEngine } from "../query/QueryEngine";
import { phasePanelModel, ROLE_LABEL, WORK_NAME } from "./model";
import { sparkline } from "./PhasePanel";

/** The hand-made fixture: the logic is tested here, where the numbers are fixed by hand. */
const fixture = JSON.parse(readFileSync(new URL("../../../data/fixtures/graph.sample.json", import.meta.url), "utf8")) as Graph;
const sample = new QueryEngine(new GraphStore(fixture));
/** The pipeline's graph: only structural facts are asserted, since its numbers change with the pipeline. */
const real = new QueryEngine(new GraphStore(GRAPH));

describe("phasePanelModel logic (fixture graph)", () => {
  const loading = phasePanelModel(sample, "phase:loadingResponse")!;

  it("names the phase in plain and formal terms", () => {
    expect(loading).toMatchObject({ id: "phase:loadingResponse", name: "loading response", commonName: "weight acceptance" });
  });

  it("knee flexion lists vastus lateralis as a braking antagonist with both names and its curve", () => {
    const knee = loading.actions.find((a) => a.id === "action:knee_flexion_r")!;
    expect(knee).toMatchObject({ name: "knee flexion", commonName: "bending the knee", rangeDeg: 15 });
    expect(knee.muscles).toHaveLength(1);
    expect(knee.muscles[0]).toMatchObject({
      id: "muscle:vaslat_r",
      name: "vastus lateralis",
      commonName: "outer quad",
      role: "antagonist",
      roleLabel: "antagonist",
      contraction: "eccentric",
      workLabel: "braking",
      peakActivation: 0.45,
    });
    expect(knee.muscles[0]!.activation).toHaveLength(11);
  });

  it("orders actions by range of motion and muscles by role, strongest first", () => {
    expect(loading.actions.map((a) => a.id)).toEqual(["action:knee_flexion_r", "action:hip_extension_r"]);
    const hip = loading.actions[1]!;
    expect(hip.muscles.map((m) => [m.id, m.role, m.workLabel])).toEqual([
      ["muscle:glmax1_r", "mainMover", "shortening"],
      ["muscle:bflh_r", "helper", "shortening"],
    ]);
  });

  it("labels stabilisers as holding", () => {
    const mid = phasePanelModel(sample, "phase:midStance")!;
    expect(mid.actions[0]!.muscles[0]).toMatchObject({ role: "stabiliser", workLabel: "holding" });
  });

  it("is undefined for an unknown id", () => {
    expect(phasePanelModel(sample, "phase:nope")).toBeUndefined();
  });
});

describe("phasePanelModel on the real graph (structure)", () => {
  const phases = real.nodesOfKind("phase");

  it("has seven phases, each with joint-action rows", () => {
    expect(phases).toHaveLength(7);
    for (const p of phases) expect(phasePanelModel(real, p.id)!.actions.length).toBeGreaterThan(0);
  });

  it("takes every role and work label from the enums, and every muscle from muscleRolesFor", () => {
    for (const p of phases) {
      const model = phasePanelModel(real, p.id)!;
      const known = new Set(real.muscleRolesFor(p.id).map((r) => `${r.jointAction.id}|${r.muscle.id}|${r.role}|${r.contraction}`));
      for (const a of model.actions) {
        for (const m of a.muscles) {
          expect(ROLE).toContain(m.role);
          expect(CONTRACTION).toContain(m.contraction);
          expect(m.roleLabel).toBe(ROLE_LABEL[m.role]);
          expect(m.workLabel).toBe(WORK_NAME[m.contraction]);
          expect(known.has(`${a.id}|${m.id}|${m.role}|${m.contraction}`)).toBe(true);
          expect(m.activation.length).toBeGreaterThan(1);
        }
      }
    }
  });

  it("lists every drivenBy edge of a phase once", () => {
    for (const p of phases) {
      const rows = phasePanelModel(real, p.id)!.actions.flatMap((a) => a.muscles);
      expect(rows).toHaveLength(real.muscleRolesFor(p.id).length);
    }
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
