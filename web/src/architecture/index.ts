import { ArchitectureView } from "./ArchitectureView";
import type { FsmId } from "./types";

let current: ArchitectureView | null = null;
const pending = new Map<FsmId, string>();

/** Mount the architecture page into `el`. */
export function mountArchitectureView(el: HTMLElement): void {
  current = new ArchitectureView(el);
  for (const [id, s] of pending) current.highlightState(id, s);
}

/** Dev-mode hook for live FSM states (TraceRecorder / E3). Remembered until the page mounts. */
export function highlightState(fsmId: FsmId, state: string): void {
  pending.set(fsmId, state);
  current?.highlightState(fsmId, state);
}

export { ArchitectureView } from "./ArchitectureView";
export { ARCHITECTURE } from "./data";
export { parseArchitecture } from "./load";
export type { Architecture, FsmId, DiagramId } from "./types";
