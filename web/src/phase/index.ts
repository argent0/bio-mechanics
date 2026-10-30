import { DynamicsPanel } from "./DynamicsPanel";
import type { Dynamics } from "./dynamics";
import { PhasePanel } from "./PhasePanel";
import type { MusclePaths } from "../timeline/clip";
import type { QueryEngine } from "../query/QueryEngine";
import type { Timeline } from "../timeline/Timeline";
import type { RegionFilter } from "../region";

export { PhasePanel, sparkline } from "./PhasePanel";
export { DynamicsPanel } from "./DynamicsPanel";
export { loadDynamics, parseDynamics, tugOfWarAt, momentScale, type Dynamics, type TugOfWar } from "./dynamics";
export { sequenceModel, sequenceGroups, type SequenceRow } from "./sequence";
export { phasePanelModel, ROLE_LABEL, WORK_NAME, type PhaseModel, type ActionRow, type MuscleRow } from "./model";

/** Mount the phase panel in `el`; it follows `timeline`'s current phase and selection. */
export function mountPhasePanel(el: HTMLElement, opts: { query: QueryEngine; timeline: Timeline; filter?: RegionFilter }): PhasePanel {
  return new PhasePanel(el, opts);
}

/** Mount the dynamics panel in `el`: the current phase's muscle sequence and the tug of war at the playhead. */
export function mountDynamicsPanel(
  el: HTMLElement,
  opts: { query: QueryEngine; timeline: Timeline; clip: MusclePaths; dynamics: Dynamics; filter?: RegionFilter },
): DynamicsPanel {
  return new DynamicsPanel(el, opts);
}
