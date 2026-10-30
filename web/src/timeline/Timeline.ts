/**
 * Timeline: the playback clock over one stride of the movement clip, the phase lookup, and
 * the UI state machine of the movement player.
 *
 * Terms: *playhead* is the current position in the stride; *percent* is the playhead in percent
 * of the stride (0-100, the unit of the graph's `hasPhase` edges); *time* is the playhead in
 * seconds of the clip (`clip.time`).
 *
 * State. `ui` is the generated UI DFA (`@gen/uiFsm`) driven through `createTracedMachine("ui")`;
 * the clock advances only in the state `playing`. The selected node belongs to the UI too: a
 * click sends `selectNode` and the selection persists while the animation plays, until
 * `closeInspector` (or `clearSelection`) clears it.
 * `gait` is the generated gait DFA (`@gen/gaitFsm`) driven through `createTracedMachine("gait")`
 * and fed the gait events as the playhead crosses phase boundaries, beginning at the initial
 * contact (decision D-001) that opens the stride. A jump of the playhead (scrub, stop) leaves
 * the gait trace; a new gait trace begins at the next initial contact the playhead reaches.
 */
import * as gait from "@gen/gaitFsm";
import * as ui from "@gen/uiFsm";
import type { QueryEngine } from "../query/QueryEngine";
import { createTracedMachine, type TraceRecorder, type TracedMachine } from "../trace";
import { findStride, type MusclePaths, type Stride } from "./clip";
import { bandIndexAtPct, eventEnding, MOVEMENT_ID, phaseBands, type PhaseBand } from "./phases";

export const SPEEDS = [0.25, 0.5, 1] as const;

export interface TimelineOptions {
  query: QueryEngine;
  clip: MusclePaths;
  movementId?: string;
  /** Wrap at the stride's end (default); `false` stops there and sends `reachEnd`. */
  loop?: boolean;
  recorder?: TraceRecorder;
}

type Listener<T> = (value: T) => void;

class Signal<T> {
  private readonly fns = new Set<Listener<T>>();
  on(fn: Listener<T>): () => void {
    this.fns.add(fn);
    return () => this.fns.delete(fn);
  }
  emit(value: T): void {
    for (const fn of this.fns) fn(value);
  }
}

export class Timeline {
  readonly clip: MusclePaths;
  readonly stride: Stride;
  readonly bands: readonly PhaseBand[];
  loop: boolean;

  private readonly recorder: TraceRecorder | undefined;
  private readonly machine: TracedMachine<"ui">;
  private gaitMachine: TracedMachine<"gait"> | null = null;
  private pctNow = 0;
  private speedNow = 1;
  private bandIdx = 0;
  private selected: string | null = null;

  private readonly timeSignal = new Signal<{ time: number; pct: number }>();
  private readonly phaseSignal = new Signal<PhaseBand>();
  private readonly uiSignal = new Signal<ui.UiState>();
  private readonly selectSignal = new Signal<string | null>();

  constructor(opts: TimelineOptions) {
    this.clip = opts.clip;
    this.stride = findStride(opts.clip);
    this.bands = phaseBands(opts.query, opts.movementId ?? MOVEMENT_ID);
    if (this.bands.length === 0) throw new Error("Timeline: the graph has no hasPhase edges");
    this.loop = opts.loop ?? true;
    this.recorder = opts.recorder;
    this.machine = createTracedMachine("ui", this.recorder);
    this.gaitMachine = createTracedMachine("gait", this.recorder);
  }

  // ---- state ----
  get state(): ui.UiState {
    return this.machine.state;
  }
  get pct(): number {
    return this.pctNow;
  }
  get time(): number {
    return this.timeOfPct(this.pctNow);
  }
  get speed(): number {
    return this.speedNow;
  }
  get phase(): PhaseBand {
    return this.bands[this.bandIdx] as PhaseBand;
  }
  get selectedId(): string | null {
    return this.selected;
  }
  /** The gait DFA state while the playhead follows a stride from its initial contact, `null` after a jump. */
  get gaitState(): gait.GaitPhase | null {
    return this.gaitMachine?.state ?? null;
  }
  get duration(): number {
    return this.stride.end - this.stride.start;
  }

  timeOfPct(pct: number): number {
    return this.stride.start + (pct / 100) * this.duration;
  }

  /** Position in the stride, in percent, of clip time `t`; times outside the stride wrap (gait repeats). */
  pctOfTime(t: number): number {
    const x = ((((t - this.stride.start) / this.duration) % 1) + 1) % 1;
    return x * 100;
  }

  /** The phase band at clip time `t`. */
  phaseAtTime(t: number): PhaseBand {
    return this.bands[bandIndexAtPct(this.bands, this.pctOfTime(t))] as PhaseBand;
  }

  // ---- subscriptions ----
  onTime(fn: Listener<{ time: number; pct: number }>): () => void {
    return this.timeSignal.on(fn);
  }
  onPhase(fn: Listener<PhaseBand>): () => void {
    return this.phaseSignal.on(fn);
  }
  onUi(fn: Listener<ui.UiState>): () => void {
    return this.uiSignal.on(fn);
  }
  onSelect(fn: Listener<string | null>): () => void {
    return this.selectSignal.on(fn);
  }

  // ---- user actions (each is one UI event) ----
  play(): void {
    if (this.send("play") === "playing" && this.pctNow >= 100) this.jump(0);
  }
  pause(): void {
    this.send("pause");
  }
  /** Rewind to the start of the stride. */
  stop(): void {
    if (this.send("stop") === "idle") this.jump(0);
  }
  scrubStart(): void {
    this.send("scrubStart");
  }
  /** Move the playhead to `pct` while scrubbing. */
  scrubTo(pct: number): void {
    if (this.state === "scrubbing") this.jump(pct);
  }
  scrubEnd(): void {
    this.send("scrubEnd");
  }
  /** Select a graph node: `selectNode`; the inspector opens and the animation holds. */
  select(nodeId: string): void {
    if (this.send("selectNode") === "inspectingNode") this.setSelected(nodeId);
  }
  closeInspector(): void {
    this.send("closeInspector");
    this.setSelected(null);
  }
  /** Drop the selection: through `closeInspector` when the inspector is open, directly otherwise. */
  clearSelection(): void {
    if (this.state === "inspectingNode") this.closeInspector();
    else this.setSelected(null);
  }
  setSpeed(speed: number): void {
    this.speedNow = speed;
  }

  /** Move the playhead without a UI event (programmatic seek, tests). */
  seek(pct: number): void {
    this.jump(pct);
  }

  /** Advance the clock by `dtSeconds` of real time; effective only in the state `playing`. */
  advance(dtSeconds: number): void {
    if (this.state !== "playing") return;
    const T = this.duration;
    const next = this.pctNow + ((dtSeconds * this.speedNow) / T) * 100;
    if (next < 100) {
      this.moveNatural(next);
    } else if (this.loop) {
      this.moveNatural(100); // closes the last phase; the wrap below opens the next stride
      this.moveNatural(next % 100);
    } else {
      this.moveNatural(100);
      this.send("reachEnd");
    }
  }

  /** Drive `advance` from `requestAnimationFrame`; returns the stop function. */
  startClock(): () => void {
    let last = performance.now();
    let id = 0;
    const frame = (now: number) => {
      this.advance(Math.min((now - last) / 1000, 0.1));
      last = now;
      id = requestAnimationFrame(frame);
    };
    id = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(id);
  }

  // ---- internals ----
  private send(event: ui.UiEvent): ui.UiState {
    const before = this.machine.state;
    const after = this.machine.send(event);
    if (after !== before) this.uiSignal.emit(after);
    return after;
  }

  private setSelected(id: string | null): void {
    if (id === this.selected) return;
    this.selected = id;
    this.selectSignal.emit(id);
  }

  /** The playhead jumps: the gait trace restarts if the target lies in the first phase, otherwise detaches. */
  private jump(pct: number): void {
    this.setPct(Math.min(100, Math.max(0, pct)));
    if (bandIndexAtPct(this.bands, this.pctNow) !== 0) this.gaitMachine = null;
    else if (this.gaitMachine === null || this.gaitMachine.state !== gait.START) this.gaitMachine = createTracedMachine("gait", this.recorder);
  }

  /** The playhead moves forward through continuous play: gait events fire at phase boundaries. */
  private moveNatural(pct: number): void {
    const wrapped = pct < this.pctNow;
    this.setPct(pct);
    const idx = this.bandIdx;
    // The wrap crosses the initial contact, which opens a gait trace (the machine starts in its first phase).
    if (this.gaitMachine === null) {
      if (!wrapped) return;
      this.gaitMachine = createTracedMachine("gait", this.recorder);
    }
    // Feed events until the machine reaches the phase under the playhead (at most one stride's worth).
    for (let guard = 0; guard < gait.PHASES.length && this.gaitMachine.state !== this.bands[idx]?.gaitPhase; guard++) {
      const e = eventEnding(this.gaitMachine.state);
      if (e === undefined) break;
      this.gaitMachine.send(e);
    }
  }

  private setPct(pct: number): void {
    this.pctNow = pct;
    const idx = bandIndexAtPct(this.bands, pct);
    const changed = idx !== this.bandIdx;
    this.bandIdx = idx;
    this.timeSignal.emit({ time: this.time, pct });
    if (changed) this.phaseSignal.emit(this.phase);
  }
}
