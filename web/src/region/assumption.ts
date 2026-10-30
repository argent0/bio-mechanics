/**
 * The head-level assumption (decision D-010): the walking trial has markers down from the
 * shoulders only, so the neck angles come from holding the head level in space. Every neck
 * muscle and neck joint action (nodes of region `head`) rests on it, and the views say so.
 */
import type { NodeAttrs } from "@gen/types";

/** Short label for a row or heading. */
export const NECK_ASSUMPTION_LABEL = "Assumes head level (D-010)";

/** Full sentence for the details pane and tooltips. */
export const NECK_ASSUMPTION_NOTE =
  "Rests on an assumption (decision D-010): the head is held level in space, because the walking trial has markers from the shoulders down and none on the head.";

/** The note for `node` when it rests on the assumption (a muscle or joint action of region `head`), else `null`. */
export function neckAssumption(node: Pick<NodeAttrs, "kind" | "region">): string | null {
  return node.region === "head" && (node.kind === "muscle" || node.kind === "jointAction") ? NECK_ASSUMPTION_NOTE : null;
}
