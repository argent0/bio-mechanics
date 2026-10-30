/**
 * Bones by region: the graph's bone nodes name their OpenSim body (`opensimName`) and carry a
 * region and side. A body (one mesh in the viewer) shows when any bone node on it passes the
 * selection: the `torso` body carries the trunk bones of both sides, so it stays visible while
 * either side stays selected. A body that no bone node names always shows.
 */
import type { NodeAttrs } from "@gen/types";
import { passes, type Placed, type RegionSelection } from "./groups";

/** Per OpenSim body name, the places of the bone nodes on that body. */
export function bodyPlacements(nodes: Iterable<Pick<NodeAttrs, "kind" | "opensimName" | "region" | "side">>): Map<string, Placed[]> {
  const out = new Map<string, Placed[]>();
  for (const n of nodes) {
    if (n.kind !== "bone" || !n.opensimName) continue;
    const list = out.get(n.opensimName) ?? [];
    list.push({ region: n.region, side: n.side });
    out.set(n.opensimName, list);
  }
  return out;
}

/** Does the body stay visible under `sel`? `placements` is the body's entry of `bodyPlacements`. */
export function bodyPasses(sel: RegionSelection, placements: readonly Placed[] | undefined): boolean {
  return !placements || placements.length === 0 || placements.some((p) => passes(sel, p));
}
