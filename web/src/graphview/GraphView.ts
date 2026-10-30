import cytoscape from "cytoscape";
import type { Kind } from "@gen/types";
import type { QueryEngine } from "../query/QueryEngine";
import { COLOURS, kindIcon } from "./icons";

/** Spacing of the selection ring: centre-to-centre distance between
 * neighbours on the ring, and the ring's smallest radius (px). */
const RING_GAP = 70;
const RING_MIN_RADIUS = 120;
/** Ring order: neighbours grouped by kind, so each kind sits in one arc. */
const KIND_ORDER: Kind[] = ["joint", "bone", "ligament", "jointAction", "phase", "movement", "muscleGroup", "muscle", "nerve"];

/** GraphView: Cytoscape view of the graph. Reads through QueryEngine only. */
export class GraphView {
  private readonly cy: cytoscape.Core;
  /** Node positions of the first layout, restored when the selection clears. */
  private home = new Map<string, cytoscape.Position>();
  private layout: cytoscape.Layouts | null = null;
  /** Milliseconds the last selection layout took to compute (excluding animation). */
  lastLayoutMs = 0;

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
    this.cy.nodes().forEach((n) => { this.home.set(n.id(), { ...n.position() }); });
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
    this.spread(id, near);
    this.showDetails(id);
  }

  /** Re-lays the whole graph around a selection: the neighbours go on a ring
   * around the selected node (grouped by kind, spaced `RING_GAP` apart) and are
   * locked there, then cose runs on the whole graph from its current positions
   * so every other node makes room; then the view fits the neighbourhood. */
  private spread(id: string, near: cytoscape.CollectionReturnValue): void {
    this.layout?.stop();
    const started = performance.now();
    const centre = this.cy.getElementById(id);
    const ring = near.nodes().difference(centre).sort((x, y) =>
      KIND_ORDER.indexOf(x.data("kind") as Kind) - KIND_ORDER.indexOf(y.data("kind") as Kind)
      || String(x.data("label")).localeCompare(String(y.data("label"))));
    const radius = Math.max(RING_MIN_RADIUS, (ring.length * RING_GAP) / (2 * Math.PI));
    const c = centre.position();
    ring.forEach((n, i) => {
      const a = (2 * Math.PI * i) / ring.length - Math.PI / 2;
      n.position({ x: c.x + radius * Math.cos(a), y: c.y + radius * Math.sin(a) });
    });
    near.nodes().lock();
    this.layout = this.cy.layout({
      name: "cose",
      randomize: false,
      animate: false,
      fit: false,
      nodeOverlap: 20,
    } as cytoscape.LayoutOptions);
    this.layout.one("layoutstop", () => {
      near.nodes().unlock();
      this.lastLayoutMs = performance.now() - started;
      this.cy.animate({ fit: { eles: near, padding: 40 }, duration: 300 });
    });
    this.layout.run();
  }

  private clear(): void {
    this.layout?.stop();
    this.cy.elements().removeClass("faded");
    this.cy.nodes().forEach((n) => {
      const p = this.home.get(n.id());
      if (p) n.animate({ position: p }, { duration: 400 });
    });
    this.cy.animate({ fit: { eles: this.cy.elements(), padding: 20 }, duration: 400 });
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
    list.className = "neighbours";
    for (const nb of this.query.neighbours(id)) {
      const a = el("a", `${nb.node.commonName ?? nb.node.name} (${nb.node.name})`) as HTMLAnchorElement;
      a.href = "#";
      a.onclick = (ev) => { ev.preventDefault(); this.focus(nb.node.id); };
      const li = el("li", nb.direction === "out" ? `${nb.edge.relation} → ` : `${nb.edge.relation} ← `);
      li.prepend(kindIcon(nb.node.kind));
      li.append(a);
      list.append(li);
    }
    const heading = el("h3", n.id);
    heading.prepend(kindIcon(n.kind));
    this.details.replaceChildren(heading, names, el("p", `kind: ${n.kind}, side: ${n.side}`), el("h4", "Neighbours"), list);
  }
}
