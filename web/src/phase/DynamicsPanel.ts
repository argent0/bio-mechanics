/**
 * DynamicsPanel: two views of the current phase that follow the Timeline.
 *
 * Sequence: one row per muscle at work in the phase (`sequence.ts`), its activation across the
 * phase as a strip of cells, darker for more activation; rows sort by peak, so the order of the
 * muscles reads top to bottom. A vertical line marks the playhead.
 *
 * Tug of war: one bar per joint coordinate (`dynamics.ts`) at the playhead. Muscles pushing
 * toward the coordinate's negative action stack left of the centre line, those pushing toward
 * its positive action stack right; each segment's width is the muscle's moment, on the bar's own
 * fixed N·m scale, its largest push over the stride (`momentScale`), printed at the bar's ends.
 * The segment's hue is its work type, from the viewer's
 * colour scale (`viewer/colour.ts`). The marker under the bar is the net moment, and the action
 * the joint is moving toward is set in bold.
 *
 * A click on a row or segment selects the muscle through the Timeline.
 */
import type { QueryEngine } from "../query/QueryEngine";
import type { MusclePaths } from "../timeline/clip";
import type { Timeline } from "../timeline/Timeline";
import { HUE, SATURATION, WORK_LABEL, type WorkType } from "../viewer/colour";
import { momentScale, tugOfWarAt, type Dynamics, type Segment, type TugOfWar } from "./dynamics";
import { sequenceModel, type SequenceRow } from "./sequence";

const CSS = `
.bm-dp { font: 13px/1.4 system-ui, sans-serif; padding: 12px; overflow: auto; }
.bm-dp h2 { margin: 0 0 4px; font-size: 16px; }
.bm-dp h2 small { font-weight: 400; font-size: 12px; color: #555; }
.bm-dp p.hint { margin: 0 0 6px; color: #555; font-size: 12px; }
.bm-dp section + section { margin-top: 18px; }
.bm-dp svg { display: block; width: 100%; }
.bm-dp [data-muscle] { cursor: pointer; }
.bm-dp .legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; color: #444; margin-top: 6px; }
.bm-dp .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
`;

const W = 400;
const LABEL_W = 170;
const CELL_H = 14;
const BAR_H = 18;
const ROW_H = 62;
const MID = W / 2;
const HALF = W / 2 - 6;

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);

/** Fill of an activation cell: one blue hue, light at rest, dark at full activation. */
export function cellFill(a: number): string {
  const x = Math.min(1, Math.max(0, a));
  return `hsl(${HUE.concentric} 70% ${(96 - 66 * x).toFixed(0)}%)`;
}

/** Fill of a moment segment: the work type's hue at mid lightness. */
export function workFill(w: WorkType): string {
  return `hsl(${HUE[w]} ${(SATURATION[w] * 100).toFixed(0)}% 50%)`;
}

export class DynamicsPanel {
  private readonly offs: (() => void)[] = [];
  private readonly scale: Map<string, number>;
  private rows: SequenceRow[] = [];
  private readonly seqEl: HTMLElement;
  private readonly tugEl: HTMLElement;

  constructor(
    private readonly el: HTMLElement,
    private readonly opts: { query: QueryEngine; timeline: Timeline; clip: MusclePaths; dynamics: Dynamics },
  ) {
    const doc = el.ownerDocument;
    if (!doc.getElementById("bm-dp-style")) doc.head.append(Object.assign(doc.createElement("style"), { id: "bm-dp-style", textContent: CSS }));
    el.classList.add("bm-dp");
    el.innerHTML = `<section data-part="sequence"></section><section data-part="tug"></section>`;
    this.seqEl = el.querySelector("[data-part=sequence]") as HTMLElement;
    this.tugEl = el.querySelector("[data-part=tug]") as HTMLElement;
    this.scale = momentScale(opts.dynamics, opts.timeline.stride);
    this.offs.push(opts.timeline.onPhase(() => this.showPhase()));
    this.offs.push(opts.timeline.onTime(() => this.tick()));
    this.offs.push(opts.timeline.onSelect(() => this.tick()));
    el.addEventListener("click", (e) => {
      const hit = (e.target as Element).closest<Element>("[data-muscle]");
      const id = hit?.getAttribute("data-muscle");
      if (id) opts.timeline.select(id);
    });
    this.showPhase();
  }

  dispose(): void {
    this.offs.forEach((f) => f());
    this.el.innerHTML = "";
  }

  private showPhase(): void {
    const band = this.opts.timeline.phase;
    this.rows = sequenceModel(this.opts.query, band.id);
    this.tick();
  }

  private tick(): void {
    this.seqEl.innerHTML = this.sequence();
    this.tugEl.innerHTML = this.tugOfWar(tugOfWarAt(this.opts.dynamics, this.opts.clip, this.opts.timeline.time));
  }

  private label(id: string): string {
    const n = this.opts.query.node(id);
    return n?.commonName ?? n?.name ?? id;
  }

  /** Row labels: the common name, or the formal name where two rows share a common name. */
  private rowLabels(): Map<string, string> {
    const count = new Map<string, number>();
    for (const r of this.rows) count.set(this.label(r.id), (count.get(this.label(r.id)) ?? 0) + 1);
    return new Map(this.rows.map((r) => [r.id, (count.get(this.label(r.id)) ?? 0) > 1 ? r.name : this.label(r.id)]));
  }

  private sequence(): string {
    const { timeline } = this.opts;
    const labels = this.rowLabels();
    const band = timeline.phase;
    const sel = timeline.selectedId;
    const cols = this.rows[0]?.activation.length ?? 0;
    const cw = cols > 0 ? (W - LABEL_W) / cols : 0;
    const h = this.rows.length * CELL_H + 16;
    const rows = this.rows
      .map((r, k) => {
        const y = k * CELL_H;
        const cells = r.activation
          .map((a, i) => `<rect x="${(LABEL_W + i * cw).toFixed(1)}" y="${y + 1}" width="${(cw - 1).toFixed(1)}" height="${CELL_H - 2}" rx="1" fill="${cellFill(a)}"/>`)
          .join("");
        const weight = r.id === sel ? "700" : "400";
        return `<g data-muscle="${esc(r.id)}"><title>${esc(this.label(r.id))} (${esc(r.name)}): peak ${r.peak.toFixed(2)} at ${(r.peakAt * 100).toFixed(0)} % of the phase</title>
          <rect x="0" y="${y}" width="${W}" height="${CELL_H}" fill="transparent"/>
          <text x="${LABEL_W - 6}" y="${y + CELL_H - 3}" text-anchor="end" font-size="10.5" font-weight="${weight}" fill="#222">${esc(labels.get(r.id) ?? r.name)}</text>${cells}</g>`;
      })
      .join("");
    const x = (timeline.pct - band.startPct) / (band.endPct - band.startPct);
    const cx = LABEL_W + Math.min(1, Math.max(0, x)) * (W - LABEL_W);
    const axis = `<text x="${LABEL_W}" y="${h - 3}" font-size="10" fill="#666">start</text><text x="${W}" y="${h - 3}" font-size="10" fill="#666" text-anchor="end">end of phase</text>`;
    const cursor = `<line x1="${cx.toFixed(1)}" x2="${cx.toFixed(1)}" y1="0" y2="${h - 14}" stroke="#111" stroke-width="1.5"/>`;
    return `<h2>Sequence <small>${esc(band.plainName)}, ${band.startPct.toFixed(0)}-${band.endPct.toFixed(0)} % of the stride</small></h2>
      <p class="hint">Activation across the phase, darker is harder; muscles in the order they peak.</p>
      <svg viewBox="0 0 ${W} ${h}" role="img" aria-label="Muscle activation across the phase">${rows}${cursor}${axis}</svg>`;
  }

  private tugOfWar(bars: TugOfWar[]): string {
    const h = bars.length * ROW_H;
    const body = bars.map((b, k) => this.bar(b, k * ROW_H)).join("");
    const legend = (Object.keys(WORK_LABEL) as WorkType[]).map((w) => `<span><i style="background:${workFill(w)}"></i>${esc(WORK_LABEL[w])}</span>`).join("");
    return `<h2>Tug of war <small>muscle moments at the playhead</small></h2>
      <p class="hint">Left pushes toward the left action, right toward the right one; the marker is the net. Each bar spans its joint's largest push in the stride. Bold: where the joint is heading.</p>
      <svg viewBox="0 0 ${W} ${h}" role="img" aria-label="Muscle moments about each joint at the playhead">${body}</svg>
      <div class="legend">${legend}</div>`;
  }

  private bar(b: TugOfWar, y0: number): string {
    const scale = this.scale.get(b.coordinate) ?? 1;
    const px = (nm: number) => (Math.abs(nm) / scale) * HALF;
    const yb = y0 + 22;
    const sel = this.opts.timeline.selectedId;
    const segs = (list: Segment[], dir: 1 | -1) => {
      let at = 0;
      return list
        .map((s) => {
          const w = px(s.moment);
          const x = dir > 0 ? MID + at : MID - at - w;
          at += w;
          if (w < 0.5) return "";
          const name = this.label(s.muscle);
          const outline = s.muscle === sel ? ` stroke="#111" stroke-width="2"` : ` stroke="#fff" stroke-width="1"`;
          const text = w > 70 ? `<text x="${(x + w / 2).toFixed(1)}" y="${yb + 13}" text-anchor="middle" font-size="10" fill="#fff" pointer-events="none">${esc(name.length > 14 ? `${name.slice(0, 13)}…` : name)}</text>` : "";
          return `<g data-muscle="${esc(s.muscle)}"><title>${esc(name)}: ${Math.abs(s.moment).toFixed(1)} N·m, activation ${s.activation.toFixed(2)}, ${esc(WORK_LABEL[s.work])}</title>
            <rect x="${x.toFixed(1)}" y="${yb}" width="${w.toFixed(1)}" height="${BAR_H}" rx="2" fill="${workFill(s.work)}"${outline}/>${text}</g>`;
        })
        .join("");
    };
    const neg = this.label(b.negative);
    const pos = this.label(b.positive);
    const bold = (side: "positive" | "negative") => (b.motion === side ? "700" : "400");
    const nx = MID + Math.sign(b.net) * Math.min(HALF, px(b.net));
    const heading = b.motion === "hold" ? "holding still" : `moving ${Math.abs(b.speedDegPerS).toFixed(0)}°/s`;
    return `<g>
      <text x="0" y="${y0 + 12}" font-size="11" font-weight="${bold("negative")}" fill="#222">◄ ${esc(neg)}</text>
      <text x="${W}" y="${y0 + 12}" font-size="11" font-weight="${bold("positive")}" fill="#222" text-anchor="end">${esc(pos)} ►</text>
      <rect x="${MID - HALF}" y="${yb}" width="${2 * HALF}" height="${BAR_H}" fill="#f3f4f6" rx="2"/>
      ${segs(b.pushNegative, -1)}${segs(b.pushPositive, 1)}
      <line x1="${MID}" x2="${MID}" y1="${yb - 3}" y2="${yb + BAR_H + 3}" stroke="#555"/>
      <path d="M ${nx.toFixed(1)} ${yb + BAR_H + 2} l -5 8 h 10 z" fill="#111"><title>net ${Math.abs(b.net).toFixed(1)} N·m</title></path>
      <text x="${MID - HALF}" y="${yb + BAR_H + 10}" font-size="9" fill="#888">${scale.toFixed(0)} N·m</text>
      <text x="${MID + HALF}" y="${yb + BAR_H + 10}" font-size="9" fill="#888" text-anchor="end">${scale.toFixed(0)} N·m</text>
      <text x="${MID}" y="${yb + BAR_H + 22}" font-size="10" fill="#555" text-anchor="middle">${esc(this.label(b.joint))} ${b.angleDeg.toFixed(0)}°, ${heading} · net ${Math.abs(b.net).toFixed(0)} N·m toward ${esc(b.net >= 0 ? pos : neg)}</text>
    </g>`;
  }
}
