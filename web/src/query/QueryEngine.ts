import type { Contraction, Edge, Kind, Node, Relation, Role } from "@gen/types";
import type { GraphStore } from "../store/GraphStore";

/** An edge of relation `R` (narrowed from the `Edge` union). */
export type EdgeOf<R extends Relation> = Extract<Edge, { relation: R }>;

/** A node next to the edge that links it to the queried node. */
export interface Neighbour {
  node: Node;
  edge: Edge;
  /** `out`: the queried node is the edge source; `in`: it is the target. */
  direction: "out" | "in";
}

export interface MuscleRole {
  muscle: Node;
  jointAction: Node;
  role: Role;
  contraction: Contraction;
  peakActivation: number;
}

export interface JointActionInPhase {
  jointAction: Node;
  rangeDeg: number;
}

/** The body parts of one joint action. */
export interface InvolvedParts {
  jointAction: Node;
  joint: Node | null;
  bones: Node[];
  muscles: { muscle: Node; role: Role; contraction: Contraction }[];
  ligaments: Node[];
}

/** QueryEngine: the only module UI components use to read the graph. */
export class QueryEngine {
  constructor(private readonly store: GraphStore) {}

  node(id: string): Node | undefined {
    return this.store.nodesById.get(id);
  }

  nodesOfKind(kind: Kind): Node[] {
    return this.store.nodesByKind.get(kind) ?? [];
  }

  allNodes(): Node[] {
    return this.store.graph.nodes;
  }

  allEdges(): Edge[] {
    return this.store.graph.edges;
  }

  edgesOf<R extends Relation>(relation: R): EdgeOf<R>[] {
    return (this.store.edgesByRelation.get(relation) ?? []) as EdgeOf<R>[];
  }

  /** Nodes one edge away, in either direction. */
  neighbours(id: string): Neighbour[] {
    const out: Neighbour[] = [];
    for (const edge of this.store.edgesBySource.get(id) ?? []) {
      const node = this.node(edge.target);
      if (node) out.push({ node, edge, direction: "out" });
    }
    for (const edge of this.store.edgesByTarget.get(id) ?? []) {
      const node = this.node(edge.source);
      if (node) out.push({ node, edge, direction: "in" });
    }
    return out;
  }

  /** Free-text lookup over anatomical and common names and ids. */
  search(text: string): Node[] {
    const q = text.trim().toLowerCase();
    if (!q) return [];
    return this.allNodes().filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        (n.commonName ?? "").toLowerCase().includes(q) ||
        n.id.toLowerCase().includes(q),
    );
  }

  /** Joint actions the phase involves, with the angle change. */
  jointActionsFor(phaseId: string): JointActionInPhase[] {
    const out: JointActionInPhase[] = [];
    for (const e of this.edgesOf("involves")) {
      const jointAction = this.node(e.target);
      if (e.source === phaseId && jointAction) out.push({ jointAction, rangeDeg: e.rangeDeg });
    }
    return out;
  }

  /** Muscle roles in a phase: the `drivenBy` edges tagged with the phase. */
  muscleRolesFor(phaseId: string): MuscleRole[] {
    const out: MuscleRole[] = [];
    for (const e of this.edgesOf("drivenBy")) {
      if (e.phase !== phaseId) continue;
      const jointAction = this.node(e.source);
      const muscle = this.node(e.target);
      if (!jointAction || !muscle) continue;
      out.push({ muscle, jointAction, role: e.role, contraction: e.contraction, peakActivation: e.peakActivation });
    }
    return out;
  }

  /** Body parts of a joint action: its joint, the joint's bones, the muscles
   * driving it with roles (one entry per `drivenBy` edge, so a muscle
   * appears once per phase), and the ligaments stabilising the joint. */
  involvedParts(jointActionId: string): InvolvedParts | undefined {
    const jointAction = this.node(jointActionId);
    if (!jointAction) return undefined;
    const joint = this.edgesOf("actionAt").filter((e) => e.source === jointActionId).map((e) => this.node(e.target))[0] ?? null;
    const bones = joint
      ? this.edgesOf("articulates").filter((e) => e.source === joint.id).flatMap((e) => this.node(e.target) ?? [])
      : [];
    const ligaments = joint
      ? this.edgesOf("stabilises").filter((e) => e.target === joint.id).flatMap((e) => this.node(e.source) ?? [])
      : [];
    const muscles = this.edgesOf("drivenBy")
      .filter((e) => e.source === jointActionId)
      .flatMap((e) => {
        const muscle = this.node(e.target);
        return muscle ? [{ muscle, role: e.role, contraction: e.contraction }] : [];
      });
    return { jointAction, joint, bones, muscles, ligaments };
  }
}
