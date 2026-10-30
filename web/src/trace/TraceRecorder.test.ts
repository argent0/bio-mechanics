/**
 * Trace tests. Set BM_TRACE_OUT=/path/trace.json to also write the recorded
 * session to a file; CI feeds it to `cd spec && lake exe conform FILE`.
 */
import { writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import * as gait from "@gen/gaitFsm";
import * as ui from "@gen/uiFsm";
import { TraceRecorder, createTracedMachine, type TraceFile } from "./TraceRecorder";

const SESSION: ui.UiEvent[] = [
  "play", "pause", "play", "scrubStart", "scrubEnd", "selectNode", "selectNode",
  "closeInspector", "play", "reachEnd", "stop", "pause",
];

describe("TraceRecorder", () => {
  it("produces the C7 shape", () => {
    const r = new TraceRecorder({ enabled: true });
    r.startTrace("ui");
    r.record("ui", "play", "playing", 5);
    const j = r.toJSON();
    expect(j).toEqual({ traces: [{ machine: "ui", steps: [{ event: "play", state: "playing", t: 5 }] }] });
  });

  it("is a no-op when disabled", () => {
    const r = new TraceRecorder({ enabled: false });
    r.startTrace("gait");
    r.record("gait", "heelOff", "terminalStance");
    expect(r.toJSON()).toEqual({ traces: [] });
  });

  it("notifies onStep listeners until unsubscribed", () => {
    const r = new TraceRecorder({ enabled: true });
    const seen: string[] = [];
    const off = r.onStep((m, s) => seen.push(`${m}:${s.event}`));
    r.record("ui", "play", "playing");
    off();
    r.record("ui", "pause", "paused");
    expect(seen).toEqual(["ui:play"]);
  });

  it("records traced machines as the generated step chain", () => {
    const r = new TraceRecorder({ enabled: true });
    const u = createTracedMachine("ui", r);
    for (const e of SESSION) u.send(e);
    const g = createTracedMachine("gait", r);
    for (const e of gait.STRIDE_WORD) g.send(e);

    const file: TraceFile = JSON.parse(JSON.stringify(r));
    expect(file.traces.map((t) => t.machine)).toEqual(["ui", "gait"]);

    let us: ui.UiState = ui.START;
    file.traces[0]!.steps.forEach((s, i) => {
      us = ui.step(us, SESSION[i]!);
      expect(s.state).toBe(us);
    });
    let gs: gait.GaitPhase = gait.START;
    file.traces[1]!.steps.forEach((s, i) => {
      gs = gait.step(gs, gait.STRIDE_WORD[i]!);
      expect(s.state).toBe(gs);
    });
    expect(gs).toBe("loadingResponse");

    const out = process.env["BM_TRACE_OUT"];
    if (out) writeFileSync(out, JSON.stringify(file, null, 2));
  });
});
