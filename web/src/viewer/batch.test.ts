import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { GRAPH } from "../config";
import { REGION } from "@gen/types";
import { parseMusclePaths } from "../timeline/clip";
import { QueryEngine } from "../query/QueryEngine";
import { GraphStore } from "../store/GraphStore";
import { batchKey, planBatches, UNPLACED } from "./batch";
import { MuscleBatch, VERTS, type BatchTube } from "./MuscleBatch";
import { RINGS, resamplePath } from "./tube";
import * as THREE from "three";

const clip = parseMusclePaths(JSON.parse(readFileSync(new URL("../../../data/out/muscle_paths.json", import.meta.url), "utf8")));
const query = new QueryEngine(new GraphStore(GRAPH));
const nodeOf = (name: string) => query.node(`muscle:${name}`);

describe("tube batching per region and side", () => {
  it("keeps the muscle draw calls at 2 per region or fewer", () => {
    const plans = planBatches(clip.muscles.keys(), nodeOf);
    expect(plans.length).toBeLessThanOrEqual(2 * REGION.length);
    expect(plans.some((p) => p.key === UNPLACED)).toBe(false);
  });

  it("places every muscle of the clip in exactly one batch", () => {
    const plans = planBatches(clip.muscles.keys(), nodeOf);
    const all = plans.flatMap((p) => p.members);
    expect(all.length).toBe(clip.muscles.size);
    expect(new Set(all).size).toBe(all.length);
  });

  it("keys by region and side, midline joining right, unknown muscles apart", () => {
    expect(batchKey({ region: "trunk", side: "left" })).toBe("trunk/left");
    expect(batchKey({ region: "trunk", side: "midline" })).toBe("trunk/right");
    expect(batchKey({ region: null, side: "right" })).toBe(UNPLACED);
    expect(batchKey(undefined)).toBe(UNPLACED);
  });

  it("builds one mesh per batch over the real clip, with the draw range following visibility", () => {
    const material = new THREE.MeshBasicMaterial();
    const batches = planBatches(clip.muscles.keys(), nodeOf).map((plan) => {
      const tubes = plan.members.map((name): BatchTube => {
        const t = clip.muscles.get(name)!;
        return { name, nodeId: `muscle:${name}`, frames: t.points.map((p) => resamplePath(p, new Float32Array(RINGS * 3))), activation: t.activation, velocity: t.velocity };
      });
      return new MuscleBatch(plan.key, tubes, material);
    });
    expect(batches.length).toBeLessThanOrEqual(10);
    const shown = batches.reduce((n, b) => n + b.visibleCount, 0);
    expect(shown).toBe(clip.muscles.size);

    const b = batches[0]!;
    const first = b.tubes[0]!;
    b.setVisible((t) => t === first);
    expect(b.visibleCount).toBe(1);
    expect(b.mesh.geometry.drawRange.count).toBe(b.mesh.geometry.index!.array.length / b.tubes.length);
    expect(b.tubeAtFace(0)).toBe(first);
    expect(b.tubeAtFace(1e6)).toBeUndefined();
    b.setVisible(() => false);
    expect(b.mesh.visible).toBe(false);
    expect(b.mesh.geometry.getAttribute("position").count).toBe(b.tubes.length * VERTS);
  });
});
