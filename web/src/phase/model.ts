/**
 * PhasePanel model: for one phase, its joint actions and per action the muscles with role and
 * work type in plain language. A pure function of the graph (through QueryEngine) and a phase id.
 */
import type { Contraction, Role } from "@gen/types";
import type { QueryEngine } from "../query/QueryEngine";

/** Role names in plain language (decision D-002 defines the roles). */
export const ROLE_LABEL: Readonly<Record<Role, string>> = {
  mainMover: "main mover",
  helper: "helper",
  stabiliser: "stabiliser",
  antagonist: "antagonist",
};

/** One line saying what each role does. */
export const ROLE_HINT: Readonly<Record<Role, string>> = {
  mainMover: "supplies most of the effort of the movement",
  helper: "adds to the main movers",
  stabiliser: "holds the joint steady while it hardly moves",
  antagonist: "pulls against the movement, often to slow it down",
};

/** Work types in plain language. */
export const WORK_NAME: Readonly<Record<Contraction, string>> = {
  concentric: "shortening",
  eccentric: "braking",
  isometric: "holding",
};

const ROLE_ORDER: readonly Role[] = ["mainMover", "helper", "stabiliser", "antagonist"];

export interface MuscleRow {
  /** Graph node id, `muscle:<name>`. */
  id: string;
  name: string;
  commonName: string | null;
  role: Role;
  roleLabel: string;
  contraction: Contraction;
  workLabel: string;
  peakActivation: number;
  /** Activation 0-1 sampled across the phase. */
  activation: number[];
}

export interface ActionRow {
  id: string;
  name: string;
  commonName: string | null;
  rangeDeg: number;
  muscles: MuscleRow[];
}

export interface PhaseModel {
  id: string;
  name: string;
  commonName: string | null;
  actions: ActionRow[];
}

export function phasePanelModel(query: QueryEngine, phaseId: string): PhaseModel | undefined {
  const phase = query.node(phaseId);
  if (!phase) return undefined;
  const driven = query.edgesOf("drivenBy").filter((e) => e.phase === phaseId);
  const actions = query
    .jointActionsFor(phaseId)
    .map(({ jointAction, rangeDeg }): ActionRow => {
      const muscles = driven
        .filter((e) => e.source === jointAction.id)
        .flatMap((e): MuscleRow[] => {
          const m = query.node(e.target);
          if (!m) return [];
          return [
            {
              id: m.id,
              name: m.name,
              commonName: m.commonName,
              role: e.role,
              roleLabel: ROLE_LABEL[e.role],
              contraction: e.contraction,
              workLabel: WORK_NAME[e.contraction],
              peakActivation: e.peakActivation,
              activation: e.activation,
            },
          ];
        })
        .sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || b.peakActivation - a.peakActivation);
      return { id: jointAction.id, name: jointAction.name, commonName: jointAction.commonName, rangeDeg, muscles };
    })
    .sort((a, b) => b.rangeDeg - a.rangeDeg);
  return { id: phase.id, name: phase.name, commonName: phase.commonName, actions };
}
