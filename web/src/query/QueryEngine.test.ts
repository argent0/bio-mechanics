import { describe, expect, it } from "vitest";
import type { Graph } from "@gen/types";
import fixture from "../../../data/fixtures/graph.sample.json";
import { GraphStore } from "../store/GraphStore";
import { QueryEngine } from "./QueryEngine";

const q = new QueryEngine(new GraphStore(fixture as unknown as Graph));

describe("QueryEngine over the fixture", () => {
  it("indexes the sample graph", () => {
    expect(q.allNodes()).toHaveLength(24);
    expect(q.allEdges()).toHaveLength(51);
    expect(q.nodesOfKind("phase").map((n) => n.id)).toContain("phase:midStance");
  });

  it("finds neighbours in both directions", () => {
    const ids = q.neighbours("joint:knee_r").map((n) => n.node.id);
    expect(ids).toContain("bone:femur_r");
    expect(ids).toContain("ligament:acl_r");
    expect(ids).toContain("action:knee_flexion_r");
  });

  it("involvedParts of knee flexion", () => {
    const p = q.involvedParts("action:knee_flexion_r");
    expect(p?.joint?.id).toBe("joint:knee_r");
    const bones = p?.bones.map((b) => b.id);
    expect(bones).toContain("bone:femur_r");
    expect(bones).toContain("bone:tibia_r");
    expect(p?.ligaments.map((l) => l.id)).toContain("ligament:acl_r");
    const vl = p?.muscles.find((m) => m.muscle.id === "muscle:vaslat_r");
    expect(vl?.role).toBe("antagonist");
    expect(vl?.contraction).toBe("eccentric");
  });

  it("muscleRolesFor and jointActionsFor a phase", () => {
    const roles = q.muscleRolesFor("phase:loadingResponse");
    expect(roles.find((r) => r.muscle.id === "muscle:glmax1_r")?.role).toBe("mainMover");
    expect(q.muscleRolesFor("phase:midStance").map((r) => r.muscle.id)).toEqual(["muscle:glmed1_r"]);
    expect(q.jointActionsFor("phase:loadingResponse")).toHaveLength(2);
  });

  it("searches by either name", () => {
    expect(q.search("walking")[0]?.id).toBe("movement:walking");
    expect(q.search("gluteus medius").map((n) => n.id)).toContain("muscle:glmed1_r");
    expect(q.search("kneecap").map((n) => n.id)).toContain("bone:patella_r");
  });
});
