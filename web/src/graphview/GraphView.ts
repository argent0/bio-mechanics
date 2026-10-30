import cytoscape from "cytoscape";
import type { Kind } from "@gen/types";
import type { QueryEngine } from "../query/QueryEngine";

const COLOURS: Record<Kind, string> = {
  bone: "#b8b8b8", joint: "#e0a030", muscle: "#d05050", muscleGroup: "#e08080",
  ligament: "#70a060", nerve: "#e0d040", movement: "#4060c0", phase: "#6080e0", jointAction: "#40a0c0",
};

/** GraphView: Cytoscape view of the graph. Reads through QueryEngine only. */
export class GraphView {
  private readonly cy: cytoscape.Core;

  constructor(container: HTMLElement, private readonly query: QueryEngine, private readonly details: HTMLElement) {
    this.cy = cytoscape({
      container,
      elements: [
        ...query.allNodes().map((n) => ({ data: { id: n.id, label: n.commonName ?? n.name, kind: n.kind } })),
        ...query.allEdges().map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target, label: e.relation } })),
      ],
      style: [
        { selector: "node", style: { label: "data(label)", "font-size": 9, "background-color": (n: cytoscape.NodeSingular) => COLOURS[n.data("kind") as Kind] } },
        { selector: "edge", style: { width: 1, "line-color": "#bbb", "target-arrow-shape": "triangle", "target-arrow-color": "#bbb", "curve-style": "bezier" } },
        { selector: ".faded", style: { opacity: 0.12 } },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#000" } },
      ],
      layout: { name: "cose", animate: false },
    });
    this.cy.on("tap", "node", (ev) => this.focus(ev.target.id() as string));
    this.cy.on("tap", (ev) => { if (ev.target === this.cy) this.clear(); });
  }

  /** Select a node, show it with its neighbours, and fill the details pane. */
  focus(id: string): void {
    const node = this.query.node(id);
    if (!node) return;
    const near = this.cy.getElementById(id).closedNeighborhood();
    this.cy.elements().addClass("faded");
    near.removeClass("faded");
    this.cy.$(":selected").unselect();
    this.cy.getElementById(id).select();
    this.cy.animate({ fit: { eles: near, padding: 40 }, duration: 250 });
    this.showDetails(id);
  }

  private clear(): void {
    this.cy.elements().removeClass("faded");
    this.details.textContent = "Click a node.";
  }

  private showDetails(id: string): void {
    const n = this.query.node(id);
    if (!n) return;
    const el = (tag: string, text: string) => Object.assign(document.createElement(tag), { textContent: text });
    const names = el("div", "");
    names.className = "names";
    const anat = el("div", ""), common = el("div", "");
    anat.append(el("dt", "Anatomical name"), el("dd", n.name));
    common.append(el("dt", "Common name"), el("dd", n.commonName ?? "-"));
    names.append(anat, common);
    const list = el("ul", "");
    for (const nb of this.query.neighbours(id)) {
      const a = el("a", `${nb.node.commonName ?? nb.node.name} (${nb.node.name})`) as HTMLAnchorElement;
      a.href = "#";
      a.onclick = (ev) => { ev.preventDefault(); this.focus(nb.node.id); };
      const li = el("li", nb.direction === "out" ? `${nb.edge.relation} → ` : `${nb.edge.relation} ← `);
      li.append(a);
      list.append(li);
    }
    this.details.replaceChildren(el("h3", n.id), names, el("p", `kind: ${n.kind}, side: ${n.side}`), el("h4", "Neighbours"), list);
  }
}
