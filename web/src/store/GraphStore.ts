import type { Edge, Graph, Kind, Node, Relation } from "@gen/types";

/** GraphStore: holds a `Graph` and indexes it. Read through QueryEngine. */
export class GraphStore {
  readonly nodesById = new Map<string, Node>();
  readonly nodesByKind = new Map<Kind, Node[]>();
  readonly edgesBySource = new Map<string, Edge[]>();
  readonly edgesByTarget = new Map<string, Edge[]>();
  readonly edgesByRelation = new Map<Relation, Edge[]>();

  constructor(readonly graph: Graph) {
    for (const n of graph.nodes) {
      this.nodesById.set(n.id, n);
      push(this.nodesByKind, n.kind, n);
    }
    for (const e of graph.edges) {
      push(this.edgesBySource, e.source, e);
      push(this.edgesByTarget, e.target, e);
      push(this.edgesByRelation, e.relation, e);
    }
  }
}

function push<K, V>(m: Map<K, V[]>, k: K, v: V): void {
  const list = m.get(k);
  if (list) list.push(v);
  else m.set(k, [v]);
}
