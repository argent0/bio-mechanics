/**
 * Draw batches of the muscle tubes: one batch per region and side, so the muscles cost at most
 * two draw calls per region (left and right) whatever their number. A muscle with no graph
 * node (or none with a region) joins the batch `unplaced`; a midline muscle joins the right one.
 */
import type { NodeAttrs } from "@gen/types";

export interface BatchPlan {
  key: string;
  /** Muscle names (the clip's keys), in input order. */
  members: string[];
}

export const UNPLACED = "unplaced";

/** The batch a muscle belongs to, from its node (if it has one). */
export function batchKey(node: Pick<NodeAttrs, "region" | "side"> | undefined): string {
  if (!node || node.region === null) return UNPLACED;
  return `${node.region}/${node.side === "left" ? "left" : "right"}`;
}

/** Group `names` into batches by `nodeOf`; batches appear in order of first member. */
export function planBatches(names: Iterable<string>, nodeOf: (name: string) => Pick<NodeAttrs, "region" | "side"> | undefined): BatchPlan[] {
  const byKey = new Map<string, BatchPlan>();
  for (const name of names) {
    const key = batchKey(nodeOf(name));
    let plan = byKey.get(key);
    if (!plan) byKey.set(key, (plan = { key, members: [] }));
    plan.members.push(name);
  }
  return [...byKey.values()];
}
