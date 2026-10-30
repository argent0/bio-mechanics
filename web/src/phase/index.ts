import { PhasePanel } from "./PhasePanel";
import type { QueryEngine } from "../query/QueryEngine";
import type { Timeline } from "../timeline/Timeline";

export { PhasePanel, sparkline } from "./PhasePanel";
export { phasePanelModel, ROLE_LABEL, WORK_NAME, type PhaseModel, type ActionRow, type MuscleRow } from "./model";

/** Mount the phase panel in `el`; it follows `timeline`'s current phase and selection. */
export function mountPhasePanel(el: HTMLElement, opts: { query: QueryEngine; timeline: Timeline }): PhasePanel {
  return new PhasePanel(el, opts);
}
