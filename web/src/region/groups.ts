/**
 * Region and side vocabulary shared by the views: display names, display order, the test a node
 * passes, and the grouping of items by region and side. Pure functions of `NodeAttrs`.
 *
 * Terms: a *selection* is the set of regions and the set of sides that stay visible. A node with
 * no region (a movement or a phase) belongs to the whole body, so every selection keeps it.
 */
import { REGION, SIDE, type NodeAttrs, type Region, type Side } from "@gen/types";

/** Region names in plain language. */
export const REGION_LABEL: Readonly<Record<Region, string>> = {
  lowerLimb: "Lower limb",
  pelvis: "Pelvis",
  trunk: "Trunk",
  upperLimb: "Upper limb",
  head: "Head",
};

/** Side names in plain language. */
export const SIDE_LABEL: Readonly<Record<Side, string>> = { right: "right", left: "left", midline: "midline" };

/** Display order of the sides: the reference (right) side first. */
export const SIDE_ORDER: readonly Side[] = ["right", "left", "midline"] as const;

/** The part of `NodeAttrs` that places a node on the body. */
export type Placed = Pick<NodeAttrs, "region" | "side">;

export interface RegionSelection {
  regions: ReadonlySet<Region>;
  sides: ReadonlySet<Side>;
}

/** The selection that keeps every region and side. */
export function everything(): RegionSelection {
  return { regions: new Set(REGION), sides: new Set(SIDE) };
}

/** Does `node` stay visible under `sel`? */
export function passes(sel: RegionSelection, node: Placed): boolean {
  return node.region === null || (sel.regions.has(node.region) && sel.sides.has(node.side));
}

/** The nodes that stay visible under `sel`, in their order. */
export function filterNodes<T extends Placed>(sel: RegionSelection, nodes: readonly T[]): T[] {
  return nodes.filter((n) => passes(sel, n));
}

/** Heading of a group, e.g. "Lower limb, right". */
export function groupHeading(region: Region | null, side: Side): string {
  return region === null ? "Whole body" : `${REGION_LABEL[region]}, ${SIDE_LABEL[side]}`;
}

export interface Group<T> {
  region: Region | null;
  side: Side;
  heading: string;
  items: T[];
}

/** Items grouped by region (in `REGION` order) and side (right, left, midline); a group with no
 * item is left out, and items without a region close the list as "Whole body". */
export function groupByRegionSide<T>(items: readonly T[], placed: (item: T) => Placed): Group<T>[] {
  const groups: Group<T>[] = [];
  for (const region of [...REGION, null]) {
    for (const side of SIDE_ORDER) {
      const members = items.filter((it) => {
        const p = placed(it);
        return p.region === region && p.side === side;
      });
      if (members.length) groups.push({ region, side, heading: groupHeading(region, side), items: members });
    }
  }
  return groups;
}
