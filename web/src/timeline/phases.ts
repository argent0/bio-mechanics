/**
 * Phase bands: the gait phases of the movement in stride order, read from the graph's
 * `hasPhase` edges (`startPct`, `endPct` in percent of the stride), and the lookup of the
 * band at a position in the stride.
 */
import type { Contraction } from "@gen/types";
import * as gait from "@gen/gaitFsm";
import type { QueryEngine } from "../query/QueryEngine";

export const MOVEMENT_ID = "movement:walking";

export interface PhaseBand {
  /** Graph node id, `phase:<GaitPhase constructor>`. */
  id: string;
  /** The generated gait DFA state of this phase. */
  gaitPhase: gait.GaitPhase;
  order: number;
  startPct: number;
  endPct: number;
  /** Formal name, e.g. "loading response". */
  name: string;
  /** Plain-language name, e.g. "weight acceptance" (falls back to the formal name). */
  plainName: string;
}

export type { Contraction };

/** The bands of `movementId` in stride order. */
export function phaseBands(query: QueryEngine, movementId: string = MOVEMENT_ID): PhaseBand[] {
  const bands: PhaseBand[] = [];
  for (const e of query.edgesOf("hasPhase")) {
    if (e.source !== movementId) continue;
    const node = query.node(e.target);
    if (!node) continue;
    const ctor = e.target.slice(e.target.indexOf(":") + 1) as gait.GaitPhase;
    bands.push({
      id: e.target,
      gaitPhase: ctor,
      order: e.order,
      startPct: e.startPct,
      endPct: e.endPct,
      name: node.name,
      plainName: node.commonName ?? node.name,
    });
  }
  return bands.sort((a, b) => a.order - b.order);
}

/** Index of the band holding `pct` (percent of the stride, half-open `[start, end)`; 100 belongs to the last band). */
export function bandIndexAtPct(bands: readonly PhaseBand[], pct: number): number {
  let idx = 0;
  bands.forEach((b, i) => {
    if (pct >= b.startPct) idx = i;
  });
  return idx;
}

/** The gait event that ends `phase` in the generated DFA (the one move to a valid phase). */
export function eventEnding(phase: gait.GaitPhase): gait.GaitEvent | undefined {
  return gait.EVENTS.find((e) => gait.step(phase, e) !== "invalid");
}
