import cytoscape from "cytoscape";
import type { Edge, Kind, Period } from "@gen/types";
import type { QueryEngine } from "../query/QueryEngine";
import { COLOURS, kindIcon } from "./icons";

/** Spacing of the selection ring: centre-to-centre distance between
 * neighbours on the ring, and the ring's smallest radius (px). */
const RING_GAP = 70;
const RING_MIN_RADIUS = 120;
/** Ring order: neighbours grouped by kind, so each kind sits in one arc. */
const KIND_ORDER: Kind[] = ["joint", "bone", "ligament", "jointAction", "phase", "movement", "muscleGroup", "muscle", "nerve"];
/** Smallest radius of the phase cycle, and the distance from the cycle out to
 * the arc of the selected phase's other neighbours (px). */
const CYCLE_MIN_RADIUS = 220;
const ARC_OFFSET = 200;
/** Width of a period band behind the phase ring (px at zoom 1). */
const BAND_WIDTH = 90;
/** Band fill per period: translucent, so it reads on light and dark backgrounds. */
const BAND_COLOURS: Record<Period, string> = { stance: "rgba(230, 140, 40, 0.22)", swing: "rgba(60, 140, 230, 0.22)" };
const SVG_NS = "http://www.w3.org/2000/svg";

/** The period bands of the cycle layout, in model coordinates around the movement node. */
interface Bands {
  hub: string;
  radius: number;
  /** Number of phases on the ring. */
  n: number;
  /** Each band runs from ring position `first` to `last`, inclusive. */
  spans: { period: Period; first: number; last: number; label: string }[];
}

/** A camel-case identifier in words, e.g. `oppositeToeOff` → "opposite toe off". */
export function words(camel: string): string {
  return camel.replace(/([A-Z])/g, " $1").toLowerCase();
}

/** Edge text: the gait event for `precedes`, the relation for every other edge. */
function edgeLabel(e: Edge): string {
  return e.relation === "precedes" ? words(e.event) : e.relation;
}

/** Positions `n` points on an arc of `radius` around `c`, centred on angle
 * `mid` and spaced `RING_GAP` apart; a full ring when they need more room. */
function arc(n: number, c: cytoscape.Position, radius: number, mid: number): cytoscape.Position[] {
  const step = Math.min(RING_GAP / radius, (2 * Math.PI) / Math.max(n, 1));
  return Array.from({ length: n }, (_, i) => {
    const a = mid + (i - (n - 1) / 2) * step;
    return { x: c.x + radius * Math.cos(a), y: c.y + radius * Math.sin(a) };
  });
}

/** Angle of position `i` of `n` on a ring, clockwise from the top. */
function clock(i: number, n: number): number {
  return (2 * Math.PI * i) / n - Math.PI / 2;
}

/** GraphView: Cytoscape view of the graph. Reads through QueryEngine only. */
export class GraphView {
  private readonly cy: cytoscape.Core;
  /** Node positions of the first layout, restored when the selection clears. */
  private home = new Map<string, cytoscape.Position>();
  private layout: cytoscape.Layouts | null = null;
  /** Milliseconds the last selection layout took to compute (excluding animation). */
  lastLayoutMs = 0;
  /** SVG layer under the graph canvas that draws `bands`. */
  private readonly bandLayer: SVGSVGElement;
  private bands: Bands | null = null;

  constructor(container: HTMLElement, private readonly query: QueryEngine, private readonly details: HTMLElement) {
    this.bandLayer = document.createElementNS(SVG_NS, "svg");
    Object.assign(this.bandLayer.style, { position: "absolute", inset: "0", width: "100%", height: "100%", pointerEvents: "none" });
    container.style.position = "relative";
    container.append(this.bandLayer);
    this.cy = cytoscape({
      container,
      elements: [
        ...query.allNodes().map((n) => ({ data: { id: n.id, label: this.nodeLabel(n.id), kind: n.kind } })),
        ...query.allEdges().map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target, relation: e.relation, label: edgeLabel(e), boundary: this.crossesPeriods(e) } })),
      ],
      style: [
        { selector: "node", style: { label: "data(label)", "font-size": 9, "text-wrap": "wrap", "text-halign": "center", "background-color": (n: cytoscape.NodeSingular) => COLOURS[n.data("kind") as Kind] } },
        { selector: "edge", style: { width: 1, "line-color": "#bbb", "target-arrow-shape": "triangle", "target-arrow-color": "#bbb", "curve-style": "bezier" } },
        { selector: "edge[relation = 'precedes']", style: { width: 2, "line-color": "#666", "target-arrow-color": "#666", label: "data(label)", "font-size": 7, "text-rotation": "autorotate", "text-background-color": "#fff", "text-background-opacity": 1 } },
        { selector: "edge[?boundary]", style: { width: 4 } },
        { selector: ".faded", style: { opacity: 0.12 } },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#000" } },
      ],
      layout: { name: "cose", animate: false },
    });
    this.cy.nodes().forEach((n) => { this.home.set(n.id(), { ...n.position() }); });
    this.cy.on("tap", "node", (ev) => this.focus(ev.target.id() as string));
    this.cy.on("tap", (ev) => { if (ev.target === this.cy) this.clear(); });
    this.cy.on("render", () => this.drawBands());
  }

  /** A `precedes` edge from a phase of one period to a phase of the other. */
  private crossesPeriods(e: Edge): boolean {
    if (e.relation !== "precedes") return false;
    const phases = this.query.phaseCycle(e.source)?.phases ?? [];
    const period = (id: string) => phases.find((p) => p.phase.id === id)?.period;
    return period(e.source) !== period(e.target);
  }

  /** Draws `bands` in rendered coordinates: one arc per period behind its run
   * of phases, labelled along the band with the period and its span. */
  private drawBands(): void {
    const b = this.bands;
    if (!b) { this.bandLayer.replaceChildren(); return; }
    const z = this.cy.zoom();
    const c = this.cy.getElementById(b.hub).renderedPosition();
    const r = b.radius * z;
    const half = Math.PI / b.n;
    const at = (a: number, rr: number) => `${c.x + rr * Math.cos(a)} ${c.y + rr * Math.sin(a)}`;
    const set = (el: Element, attrs: Record<string, string>) => { for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v); };
    const children = b.spans.flatMap((s, k) => {
      const from = clock(s.first, b.n) - half, to = clock(s.last, b.n) + half;
      const large = to - from > Math.PI ? 1 : 0;
      const path = document.createElementNS(SVG_NS, "path");
      set(path, { d: `M ${at(from, r)} A ${r} ${r} 0 ${large} 1 ${at(to, r)}`, fill: "none", stroke: BAND_COLOURS[s.period], "stroke-width": String(BAND_WIDTH * z) });
      // The label runs along the outer part of the band, clear of the phase nodes on the ring.
      const rl = r + BAND_WIDTH * 0.3 * z;
      const guide = document.createElementNS(SVG_NS, "path");
      set(guide, { id: `band-label-${k}`, d: `M ${at(from, rl)} A ${rl} ${rl} 0 ${large} 1 ${at(to, rl)}`, fill: "none" });
      const text = document.createElementNS(SVG_NS, "text");
      set(text, { fill: "#888", "font-size": String(14 * z), "dominant-baseline": "middle" });
      const onPath = document.createElementNS(SVG_NS, "textPath");
      set(onPath, { href: `#band-label-${k}`, startOffset: "50%", "text-anchor": "middle" });
      onPath.textContent = s.label;
      text.append(onPath);
      return [path, guide, text];
    });
    this.bandLayer.replaceChildren(...children);
  }

  /** Node text: the common name, plus the span in percent of the cycle for a phase. */
  private nodeLabel(id: string): string {
    const n = this.query.node(id);
    if (!n) return id;
    const name = n.commonName ?? n.name;
    const p = this.query.phaseCycle(id)?.phases.find((x) => x.phase.id === id);
    return p ? `${name}\n${Math.round(p.startPct)}–${Math.round(p.endPct)} %` : name;
  }

  /** The elements a selection shows: the node with its neighbours, plus, for a
   * movement or phase, the whole phase cycle with its movement. */
  private neighbourhood(id: string): cytoscape.CollectionReturnValue {
    let near = this.cy.getElementById(id).closedNeighborhood();
    const cycle = this.query.phaseCycle(id);
    if (cycle) {
      let ring = this.cy.getElementById(cycle.movement.id).union(this.cy.collection());
      for (const p of cycle.phases) ring = ring.union(this.cy.getElementById(p.phase.id));
      near = near.union(ring).union(ring.edgesWith(ring));
    }
    return near;
  }

  /** Select a node, show it with its neighbours, and fill the details pane. */
  focus(id: string): void {
    const node = this.query.node(id);
    if (!node) return;
    const near = this.neighbourhood(id);
    this.cy.elements().addClass("faded");
    near.removeClass("faded");
    this.cy.$(":selected").unselect();
    this.cy.getElementById(id).select();
    this.spread(id, near);
    this.showDetails(id);
  }

  /** Re-lays the whole graph around a selection: `place` puts the shown nodes
   * in position and they are locked there, then cose runs on the whole graph
   * from its current positions so every other node makes room; then the view
   * fits the shown elements. */
  private spread(id: string, near: cytoscape.CollectionReturnValue): void {
    this.layout?.stop();
    const started = performance.now();
    this.place(id, near.nodes());
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
      this.cy.animate({ fit: { eles: near, padding: this.bands ? 60 : 40 }, duration: 300 });
    });
    this.layout.run();
  }

  /** Positions of the shown nodes. A movement or phase gets the cycle layout:
   * the phases clockwise from the top in cycle order on a ring around their
   * movement, and the selected phase's other neighbours on an arc outside it.
   * Every other node gets a ring of its neighbours, grouped by kind and spaced
   * `RING_GAP` apart. */
  private place(id: string, shown: cytoscape.NodeCollection): void {
    const centre = this.cy.getElementById(id);
    const cycle = this.query.phaseCycle(id);
    const byKind = (x: cytoscape.NodeSingular, y: cytoscape.NodeSingular) =>
      KIND_ORDER.indexOf(x.data("kind") as Kind) - KIND_ORDER.indexOf(y.data("kind") as Kind)
      || String(x.data("label")).localeCompare(String(y.data("label")));
    if (!cycle) {
      const ring = shown.difference(centre).sort(byKind);
      const radius = Math.max(RING_MIN_RADIUS, (ring.length * RING_GAP) / (2 * Math.PI));
      const c = centre.position();
      ring.forEach((n, i) => { n.position({ x: c.x + radius * Math.cos(clock(i, ring.length)), y: c.y + radius * Math.sin(clock(i, ring.length)) }); });
      this.bands = null;
      return;
    }
    const hub = this.cy.getElementById(cycle.movement.id);
    const c = { ...hub.position() };
    const n = cycle.phases.length;
    const radius = Math.max(CYCLE_MIN_RADIUS, (n * 2 * RING_GAP) / (2 * Math.PI));
    cycle.phases.forEach((p, i) => {
      this.cy.getElementById(p.phase.id).position({ x: c.x + radius * Math.cos(clock(i, n)), y: c.y + radius * Math.sin(clock(i, n)) });
    });
    const inCycle = new Set([hub.id(), ...cycle.phases.map((p) => p.phase.id)]);
    const rest = shown.filter((x) => !inCycle.has(x.id())).sort(byKind);
    const i = cycle.phases.findIndex((p) => p.phase.id === id);
    const spots = i < 0
      ? rest.map((_, k) => ({ x: c.x + (radius + ARC_OFFSET) * Math.cos(clock(k, rest.length)), y: c.y + (radius + ARC_OFFSET) * Math.sin(clock(k, rest.length)) }))
      : arc(rest.length, c, radius + ARC_OFFSET, clock(i, n));
    rest.forEach((x, k) => { const p = spots[k]; if (p) x.position(p); });
    let first = 0;
    this.bands = {
      hub: hub.id(), radius, n,
      spans: cycle.periods.map((s) => {
        const span = { period: s.period, first, last: first + s.phases.length - 1, label: `${s.period} · ${Math.round(s.startPct)}–${Math.round(s.endPct)} %` };
        first += s.phases.length;
        return span;
      }),
    };
  }

  private clear(): void {
    this.layout?.stop();
    this.bands = null;
    this.cy.elements().removeClass("faded");
    this.cy.nodes().forEach((n) => {
      const p = this.home.get(n.id());
      if (p) n.animate({ position: p }, { duration: 400 });
    });
    this.cy.animate({ fit: { eles: this.cy.elements(), padding: 20 }, duration: 400 });
    this.details.textContent = "Click a node.";
  }

  /** What tells parallel edges apart in the neighbour list: the coordinate of
   * `crosses`, the phase of `drivenBy`, the gait event of `precedes`. */
  private qualifier(e: Edge): string[] {
    switch (e.relation) {
      case "crosses": return [e.coordinate.replace(/_[lr]$/, "").replaceAll("_", " ")];
      case "drivenBy": { const p = this.query.node(e.phase); return [p?.commonName ?? p?.name ?? e.phase]; }
      case "precedes": return [`at ${words(e.event)}`];
      default: return [];
    }
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
    for (const nb of this.query.groupedNeighbours(id)) {
      const a = el("a", `${nb.node.commonName ?? nb.node.name} (${nb.node.name})`) as HTMLAnchorElement;
      a.href = "#";
      a.onclick = (ev) => { ev.preventDefault(); this.focus(nb.node.id); };
      const li = el("li", nb.direction === "out" ? `${nb.relation} → ` : `${nb.relation} ← `);
      li.prepend(kindIcon(nb.node.kind));
      li.append(a);
      const what = [...new Set(nb.edges.flatMap((e) => this.qualifier(e)))];
      if (what.length) li.append(` · ${what.join(", ")}`);
      list.append(li);
    }
    const heading = el("h3", n.id);
    heading.prepend(kindIcon(n.kind));
    const span = this.query.phaseCycle(id)?.phases.find((p) => p.phase.id === id);
    const where = span ? [el("p", `${span.startPct.toFixed(0)}–${span.endPct.toFixed(0)} % of the cycle, phase ${span.order + 1}`)] : [];
    this.details.replaceChildren(heading, names, el("p", `kind: ${n.kind}, side: ${n.side}`), ...where, el("h4", "Neighbours"), list);
  }
}
