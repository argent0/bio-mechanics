/**
 * PhasePanel: the current phase of the Timeline with its joint actions and, per action, the
 * muscles with role and work type (model in `model.ts`). A muscle row opens its activation curve
 * (inline SVG); a click on the row selects the muscle through the Timeline, which the viewer
 * highlights.
 */
import type { QueryEngine } from "../query/QueryEngine";
import type { Timeline } from "../timeline/Timeline";
import { phasePanelModel, ROLE_HINT, type MuscleRow, type PhaseModel } from "./model";

const CSS = `
.bm-pp { font: 13px/1.4 system-ui, sans-serif; padding: 12px; overflow: auto; }
.bm-pp h2 { margin: 0; font-size: 18px; }
.bm-pp h2 small { display: block; font-weight: 400; font-size: 13px; color: #555; }
.bm-pp h3 { margin: 14px 0 4px; font-size: 14px; }
.bm-pp h3 small { font-weight: 400; color: #555; }
.bm-pp ul { list-style: none; margin: 0; padding: 0; }
.bm-pp li { border-top: 1px solid #e3e6ea; }
.bm-pp .row { display: grid; grid-template-columns: 5.6em 1fr auto auto; gap: 8px; align-items: baseline; padding: 4px 4px; cursor: pointer; }
.bm-pp .row:hover { background: #f1f4f8; }
.bm-pp li[data-selected="true"] > .row { background: #fff1d6; }
.bm-pp .role { font-weight: 600; font-size: 12px; }
.bm-pp .role[data-role="mainMover"] { color: #1d4f91; }
.bm-pp .role[data-role="helper"] { color: #2f6f5b; }
.bm-pp .role[data-role="stabiliser"] { color: #6b4d9c; }
.bm-pp .role[data-role="antagonist"] { color: #a24a12; }
.bm-pp .work[data-work="eccentric"] { color: #a24a12; }
.bm-pp .work[data-work="concentric"] { color: #1d4f91; }
.bm-pp .names span { display: block; }
.bm-pp .names small { display: block; color: #666; }
.bm-pp button.curve { font: inherit; font-size: 12px; padding: 0 6px; }
.bm-pp .spark { padding: 2px 8px 6px 5.6em; color: #444; }
.bm-pp .spark svg { display: block; width: 100%; max-width: 280px; height: 56px; background: #f6f8fa; border-radius: 3px; }
`;

const SVG_W = 200;
const SVG_H = 50;

/** Inline sparkline of an activation curve (0-1) across the phase. */
export function sparkline(values: readonly number[]): string {
  const n = values.length;
  if (n < 2) return "";
  const pts = values.map((v, i) => `${((i / (n - 1)) * SVG_W).toFixed(1)},${(SVG_H - Math.min(1, Math.max(0, v)) * (SVG_H - 4) - 2).toFixed(1)}`);
  return `<svg viewBox="0 0 ${SVG_W} ${SVG_H}" preserveAspectRatio="none" role="img" aria-label="Activation over the phase">
    <line x1="0" y1="${SVG_H - 2}" x2="${SVG_W}" y2="${SVG_H - 2}" stroke="#bbb" stroke-width="0.5"/>
    <polyline points="${pts.join(" ")}" fill="none" stroke="#1d4f91" stroke-width="1.8" vector-effect="non-scaling-stroke"/></svg>`;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);

export class PhasePanel {
  private readonly open = new Set<string>();
  private model: PhaseModel | undefined;
  private readonly offs: (() => void)[] = [];

  constructor(private readonly el: HTMLElement, private readonly opts: { query: QueryEngine; timeline: Timeline }) {
    if (!el.ownerDocument.getElementById("bm-pp-style")) {
      el.ownerDocument.head.append(Object.assign(el.ownerDocument.createElement("style"), { id: "bm-pp-style", textContent: CSS }));
    }
    el.classList.add("bm-pp");
    this.offs.push(opts.timeline.onPhase((band) => this.show(band.id)));
    this.offs.push(opts.timeline.onSelect(() => this.markSelection()));
    el.addEventListener("click", (e) => this.onClick(e));
    this.show(opts.timeline.phase.id);
  }

  dispose(): void {
    this.offs.forEach((f) => f());
    this.el.innerHTML = "";
  }

  private show(phaseId: string): void {
    this.model = phasePanelModel(this.opts.query, phaseId);
    this.el.innerHTML = this.model ? this.render(this.model) : "";
  }

  private render(m: PhaseModel): string {
    const band = this.opts.timeline.phase;
    const actions = m.actions
      .map(
        (a) => `<h3>${esc(a.commonName ?? a.name)} <small>(${esc(a.name)}, ${a.rangeDeg.toFixed(0)}&deg;)</small></h3>
        <ul>${a.muscles.map((r) => this.muscleLi(a.id, r)).join("") || "<li><em>no muscle labelled in this phase</em></li>"}</ul>`,
      )
      .join("");
    return `<h2>${esc(m.commonName ?? m.name)}<small>${esc(m.name)}, ${band.startPct.toFixed(0)}-${band.endPct.toFixed(0)} % of the stride</small></h2>${actions}`;
  }

  private muscleLi(actionId: string, r: MuscleRow): string {
    const key = `${actionId}|${r.id}`;
    const open = this.open.has(key);
    const selected = this.opts.timeline.selectedId === r.id;
    return `<li data-muscle="${esc(r.id)}" data-selected="${selected}">
      <div class="row" title="${esc(ROLE_HINT[r.role])}">
        <span class="role" data-role="${r.role}">${r.roleLabel}</span>
        <span class="names"><span>${esc(r.commonName ?? r.name)}</span><small>${esc(r.name)}</small></span>
        <span class="work" data-work="${r.contraction}">${r.workLabel}</span>
        <button class="curve" data-curve="${esc(key)}" aria-expanded="${open}">${open ? "hide curve" : "curve"}</button>
      </div>
      ${open ? `<div class="spark">${sparkline(r.activation)}<div>activation across the phase, peak ${r.peakActivation.toFixed(2)}</div></div>` : ""}
    </li>`;
  }

  private onClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    const curve = target.closest<HTMLElement>("[data-curve]");
    if (curve) {
      const id = curve.dataset["curve"] as string;
      if (!this.open.delete(id)) this.open.add(id);
      if (this.model) this.show(this.model.id);
      return;
    }
    const li = target.closest<HTMLElement>("[data-muscle]");
    if (li) this.opts.timeline.select(li.dataset["muscle"] as string);
  }

  private markSelection(): void {
    const sel = this.opts.timeline.selectedId;
    this.el.querySelectorAll<HTMLElement>("[data-muscle]").forEach((li) => (li.dataset["selected"] = String(li.dataset["muscle"] === sel)));
  }
}
