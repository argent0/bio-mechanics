/**
 * Sequence model: the muscles at work in one phase, in the order they peak. A pure function of
 * the graph (through QueryEngine) and a phase id.
 *
 * Source: the `drivenBy` edges of the phase. Each carries the muscle's activation curve sampled
 * evenly from the phase start to its end; a muscle that drives several actions carries the same
 * curve on each edge, so it appears once here.
 *
 * Terms: the *peak* is the sample of highest activation; the *onset* is the first sample where
 * activation reaches half of that peak. Rows sort by peak, then by onset.
 */
import type { QueryEngine } from "../query/QueryEngine";

export interface SequenceRow {
  /** Graph node id, `muscle:<name>`. */
  id: string;
  name: string;
  commonName: string | null;
  /** Activation 0-1, sampled evenly across the phase. */
  activation: number[];
  /** Position of the peak in the phase, 0-1. */
  peakAt: number;
  /** Position of the onset in the phase, 0-1. */
  onsetAt: number;
  peak: number;
}

export function sequenceModel(query: QueryEngine, phaseId: string): SequenceRow[] {
  const curves = new Map<string, number[]>();
  for (const e of query.edgesOf("drivenBy")) if (e.phase === phaseId && !curves.has(e.target)) curves.set(e.target, e.activation);
  const rows: SequenceRow[] = [];
  for (const [id, activation] of curves) {
    const m = query.node(id);
    const n = activation.length;
    if (!m || n < 2) continue;
    const peak = Math.max(...activation);
    const iPeak = activation.indexOf(peak);
    const iOnset = activation.findIndex((a) => a >= peak / 2);
    rows.push({ id, name: m.name, commonName: m.commonName, activation, peak, peakAt: iPeak / (n - 1), onsetAt: iOnset / (n - 1) });
  }
  return rows.sort((a, b) => a.peakAt - b.peakAt || a.onsetAt - b.onsetAt || b.peak - a.peak);
}
