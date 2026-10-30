/**
 * Dev-mode trace recorder (contract C7, format in spec/BioMech/Conform.lean).
 *
 * Terms: a *trace* is the list of steps one machine ran through; a *step* is an
 * event plus the state right after it. The start state is implied
 * (`START` of the generated table), so a trace holds steps only.
 *
 * The recorder is active when `import.meta.env.DEV` holds (or when a test
 * passes `enabled: true`); otherwise every method returns at once.
 */
import * as gait from "@gen/gaitFsm";
import * as ui from "@gen/uiFsm";

export type MachineName = "gait" | "ui";

/** Event and state unions per machine, taken from the generated tables. */
export interface MachineTypes {
  gait: { event: gait.GaitEvent; state: gait.GaitPhase };
  ui: { event: ui.UiEvent; state: ui.UiState };
}

/** One recorded step; extra keys such as `t` (ms) are free. */
export interface TraceStep<M extends MachineName = MachineName> {
  event: MachineTypes[M]["event"];
  state: MachineTypes[M]["state"];
  t?: number;
}

export interface Trace<M extends MachineName = MachineName> {
  machine: M;
  steps: TraceStep<M>[];
}

/** The `trace.json` file: input of `lake exe conform`. */
export interface TraceFile {
  traces: Trace[];
}

export type StepListener = <M extends MachineName>(
  machine: M,
  step: TraceStep<M>,
  stateAfter: MachineTypes[M]["state"],
) => void;

const devFlag = (): boolean =>
  (import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV === true;

export class TraceRecorder {
  readonly enabled: boolean;
  private traces: Trace[] = [];
  private listeners = new Set<StepListener>();
  private t0 = Date.now();

  constructor(options: { enabled?: boolean } = {}) {
    this.enabled = options.enabled ?? devFlag();
  }

  /** Begin a new trace for `machine`; its start state is implied. */
  startTrace(machine: MachineName): void {
    if (!this.enabled) return;
    this.traces.push({ machine, steps: [] });
  }

  /** Append a step to the latest trace of `machine` (started on demand). */
  record<M extends MachineName>(
    machine: M,
    event: MachineTypes[M]["event"],
    stateAfter: MachineTypes[M]["state"],
    t: number = Date.now() - this.t0,
  ): void {
    if (!this.enabled) return;
    let trace = [...this.traces].reverse().find((x) => x.machine === machine);
    if (trace === undefined) {
      this.startTrace(machine);
      trace = this.traces[this.traces.length - 1];
    }
    const step: TraceStep<M> = { event, state: stateAfter, t };
    (trace as Trace<M> | undefined)?.steps.push(step);
    for (const l of this.listeners) l(machine, step, stateAfter);
  }

  /** Observe every recorded step (for live highlighting); returns an unsubscribe. */
  onStep(listener: StepListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** The recording in the C7 shape (a deep copy). */
  toJSON(): TraceFile {
    return { traces: this.traces.map((x) => ({ machine: x.machine, steps: x.steps.map((s) => ({ ...s })) })) };
  }

  clear(): void {
    this.traces = [];
    this.t0 = Date.now();
  }

  /** Browser only: save the recording as `trace.json`. */
  download(filename = "trace.json"): void {
    if (!this.enabled || typeof document === "undefined") return;
    const blob = new Blob([JSON.stringify(this.toJSON(), null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }
}

/** The app-wide recorder; in dev mode also reachable as `window.__bmTrace`. */
export const recorder = new TraceRecorder();
if (recorder.enabled && typeof window !== "undefined") {
  (window as unknown as { __bmTrace?: TraceRecorder }).__bmTrace = recorder;
}

/** A generated FSM module, as `createTracedMachine` needs it. */
export interface FsmModule<M extends MachineName> {
  START: MachineTypes[M]["state"];
  step(state: MachineTypes[M]["state"], event: MachineTypes[M]["event"]): MachineTypes[M]["state"];
}

export interface TracedMachine<M extends MachineName> {
  readonly state: MachineTypes[M]["state"];
  send(event: MachineTypes[M]["event"]): MachineTypes[M]["state"];
}

/**
 * Drive a generated FSM and record each step. Starts a new trace.
 * `createTracedMachine("ui")` uses the generated tables; `fsm` overrides them.
 */
export function createTracedMachine<M extends MachineName>(
  machine: M,
  rec: TraceRecorder = recorder,
  fsm: FsmModule<M> = (machine === "gait" ? gait : ui) as unknown as FsmModule<M>,
): TracedMachine<M> {
  let state = fsm.START;
  rec.startTrace(machine);
  return {
    get state() {
      return state;
    },
    send(event) {
      state = fsm.step(state, event);
      rec.record(machine, event, state);
      return state;
    },
  };
}
