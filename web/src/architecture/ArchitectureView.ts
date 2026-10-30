import cytoscape from "cytoscape";
import { ARCHITECTURE } from "./data";
import { sourceLabel, sourceUrl, SOURCE_BASE_URL } from "./config";
import { DIAGRAMS, PLAIN, diagramLoc, elementsFor, moduleOf, theoremsFor } from "./elements";
import type { Architecture, DiagramId, FsmId, Loc } from "./types";

const STYLE: cytoscape.StylesheetJson = [
  { selector: "node", style: { label: "data(label)", "font-size": 10, "text-wrap": "wrap", "text-valign": "center", "text-halign": "center",
      shape: "round-rectangle", width: "label", height: "label", padding: "8px", "background-color": "#dde6f5", "border-width": 1, "border-color": "#6a7fa8" } },
  { selector: "edge", style: { width: 1.5, "line-color": "#999", "target-arrow-shape": "triangle", "target-arrow-color": "#999",
      "curve-style": "bezier", label: "data(label)", "font-size": 8, "text-background-color": "#fff", "text-background-opacity": 0.85 } },
  { selector: ".start", style: { "border-width": 3, "border-color": "#2a8a3a" } },
  { selector: ".accept", style: { "border-style": "double", "border-width": 4 } },
  { selector: ".faded", style: { opacity: 0.3 } },
  { selector: ".live", style: { "background-color": "#ffd24a", "border-color": "#c07000", "border-width": 4 } },
  { selector: "node:selected", style: { "border-color": "#000", "border-width": 3 } },
];

const h = (tag: string, props: Record<string, string> = {}, ...kids: (Node | string)[]): HTMLElement => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids);
  return e;
};

export class ArchitectureView {
  private cy: cytoscape.Core | null = null;
  private diagram: DiagramId = "schema";
  private moduleFilter = "diagram"; // "diagram" | "all" | a Lean module name
  private readonly canvas = h("div", { className: "arch-canvas" });
  private readonly info = h("div", { className: "arch-info" });
  private readonly theorems = h("div", { className: "arch-theorems" });
  private readonly tabs = h("nav", { className: "arch-tabs" });
  private readonly live = new Map<FsmId, string>();

  constructor(private readonly root: HTMLElement, private readonly arch: Architecture = ARCHITECTURE, private readonly base: string = SOURCE_BASE_URL) {
    root.classList.add("arch-view");
    root.style.cssText += "display:flex;flex-direction:column;height:100%;font-family:system-ui,sans-serif";
    this.canvas.style.cssText = "flex:1;min-height:300px";
    const side = h("aside", { className: "arch-side" }, this.info, this.theorems);
    side.style.cssText = "width:28em;overflow:auto;padding:12px;border-left:1px solid #ccc";
    this.tabs.style.cssText = "display:flex;gap:8px;padding:8px 12px;border-bottom:1px solid #ccc";
    const main = h("div", {}, this.canvas, side);
    main.style.cssText = "display:flex;flex:1;min-height:0";
    this.canvas.style.flex = "1";
    root.append(this.tabs, main);
    for (const d of DIAGRAMS) {
      const b = h("button", { textContent: PLAIN[d].title, title: d });
      b.dataset.diagram = d;
      b.addEventListener("click", () => this.show(d));
      this.tabs.append(b);
    }
    this.show("schema");
  }

  show(d: DiagramId): void {
    this.diagram = d;
    this.cy?.destroy();
    const roots = d === "gaitFsm" || d === "uiFsm" ? [`${d}:${this.arch.fsms.find((f) => f.id === d)?.start ?? ""}`] : undefined;
    this.cy = cytoscape({
      container: this.canvas, elements: elementsFor(this.arch, d), style: STYLE,
      layout: { name: d === "schema" ? "cose" : "breadthfirst", directed: true, roots, spacingFactor: 1.2, animate: false } as cytoscape.LayoutOptions,
    });
    this.cy.on("tap", "node,edge", (ev) => this.showElement(ev.target as cytoscape.SingularElementReturnValue));
    this.cy.on("tap", (ev) => { if (ev.target === this.cy) this.showDiagram(); });
    for (const b of Array.from(this.tabs.children) as HTMLElement[]) b.style.fontWeight = b.dataset.diagram === d ? "700" : "400";
    this.showDiagram();
    for (const [id, s] of this.live) if (id === d) this.highlightState(id, s);
  }

  /** Dev-mode hook: mark the live state of an FSM (shown when that FSM's diagram is open). */
  highlightState(fsmId: FsmId, state: string): void {
    this.live.set(fsmId, state);
    if (this.diagram !== fsmId || !this.cy) return;
    this.cy.nodes().removeClass("live");
    this.cy.getElementById(`${fsmId}:${state}`).addClass("live");
  }

  private sourceLink(loc: Loc): HTMLElement {
    const url = sourceUrl(loc, this.base);
    const text = sourceLabel(loc);
    return url ? h("a", { href: url, textContent: text, target: "_blank" }) : h("code", { textContent: text });
  }

  private showDiagram(): void {
    const d = this.diagram, p = PLAIN[d];
    this.info.replaceChildren(h("h3", { textContent: p.title }), h("p", { textContent: p.blurb }),
      h("div", {}, "Lean source: ", this.sourceLink(diagramLoc(this.arch, d))), h("div", { textContent: `Formal name: ${d}` }));
    this.renderTheorems();
  }

  private showElement(el: cytoscape.SingularElementReturnValue): void {
    const loc = el.data("loc") as Loc | null;
    const d = el.data("doc") as string;
    this.info.replaceChildren(h("h3", { textContent: String(el.data("label")).split("\n")[0] ?? "" }),
      ...(d ? [h("p", { textContent: d })] : []),
      ...(loc ? [h("div", {}, "Lean source: ", this.sourceLink(loc))] : []));
  }

  private renderTheorems(): void {
    const diagMod = moduleOf(this.arch, this.diagram);
    const module = this.moduleFilter === "diagram" ? diagMod : this.moduleFilter === "all" ? null : this.moduleFilter;
    const sel = h("select") as HTMLSelectElement;
    sel.append(h("option", { value: "diagram", textContent: `Module behind this diagram (${diagMod})` }),
      h("option", { value: "all", textContent: "All modules" }));
    for (const m of new Set(this.arch.theorems.map((t) => t.loc.module))) sel.append(h("option", { value: m, textContent: m }));
    sel.value = this.moduleFilter;
    sel.addEventListener("change", () => { this.moduleFilter = sel.value; this.renderTheorems(); });
    const list = theoremsFor(this.arch, module);
    this.theorems.replaceChildren(h("h4", { textContent: `Proved properties (${list.length})` }), sel,
      ...list.map((t) => {
        const box = h("details", {}, h("summary", { textContent: t.name }),
          h("pre", { textContent: t.statement }), h("p", { textContent: t.doc ?? "" }), this.sourceLink(t.loc));
        box.querySelector("pre")!.style.cssText = "white-space:pre-wrap;font-family:monospace;font-size:11px";
        return box;
      }));
  }
}
