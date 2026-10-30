import { describe, expect, it } from "vitest";
import * as gait from "@gen/gaitFsm";
import * as ui from "@gen/uiFsm";
import { GRAPH } from "../config";
import { GraphStore } from "../store/GraphStore";
import { QueryEngine } from "../query/QueryEngine";
import { TraceRecorder } from "../trace";
import { readFileSync } from "node:fs";
import { parseMusclePaths } from "./clip";
import { bandIndexAtPct, phaseBands } from "./phases";
import { Timeline } from "./Timeline";

const query = new QueryEngine(new GraphStore(GRAPH));
const clip = parseMusclePaths(JSON.parse(readFileSync(new URL("../../../data/out/muscle_paths.json", import.meta.url), "utf8")));

const edges = query.edgesOf("hasPhase");

function make(loop = true) {
  const recorder = new TraceRecorder({ enabled: true });
  const timeline = new Timeline({ query, clip, recorder, loop });
  return { recorder, timeline };
}

describe("phase bands", () => {
  const bands = phaseBands(query);

  it("are the seven hasPhase edges in stride order with plain and formal names", () => {
    expect(bands.map((b) => b.id)).toEqual(gait.PHASES.map((p) => `phase:${p}`));
    expect(bands.map((b) => b.gaitPhase)).toEqual([...gait.PHASES]);
    expect(bands[0]).toMatchObject({ name: "loading response", plainName: "weight acceptance", startPct: 0 });
    expect(bands[6]?.endPct).toBe(100);
  });

  it("lookup by percent follows the graph's boundaries, half-open", () => {
    for (const e of edges) {
      const i = bands.findIndex((b) => b.id === e.target);
      expect(bandIndexAtPct(bands, e.startPct)).toBe(i);
      expect(bandIndexAtPct(bands, (e.startPct + e.endPct) / 2)).toBe(i);
      expect(bandIndexAtPct(bands, e.endPct - 1e-6)).toBe(i);
    }
    expect(bandIndexAtPct(bands, 100)).toBe(6);
    expect(bandIndexAtPct(bands, 0)).toBe(0);
  });

  it("lookup by clip time maps through the stride (wrapping outside it)", () => {
    const { timeline } = make();
    const { start, end } = timeline.stride;
    const T = end - start;
    for (const e of edges) {
      const mid = start + (((e.startPct + e.endPct) / 2) / 100) * T;
      expect(timeline.phaseAtTime(mid).id).toBe(e.target);
    }
    // 0.1 s before the stride begins lies in the previous stride's terminal swing.
    expect(timeline.phaseAtTime(start - 0.1).id).toBe("phase:terminalSwing");
    expect(timeline.phaseAtTime(start).id).toBe("phase:loadingResponse");
  });
});

describe("Timeline UI events", () => {
  it("record the generated step chain", () => {
    const { recorder, timeline } = make(false);
    timeline.play();
    timeline.pause();
    timeline.play();
    timeline.scrubStart();
    timeline.scrubTo(40);
    timeline.scrubEnd();
    timeline.select("muscle:vaslat_r");
    timeline.select("muscle:recfem_r");
    timeline.closeInspector();
    timeline.play();
    timeline.advance(10); // past the end, no loop: reachEnd
    timeline.stop();
    const trace = recorder.toJSON().traces.find((t) => t.machine === "ui")!;
    const events = trace.steps.map((s) => s.event);
    expect(events).toEqual(["play", "pause", "play", "scrubStart", "scrubEnd", "selectNode", "selectNode", "closeInspector", "play", "reachEnd", "stop"]);
    let state: ui.UiState = ui.START;
    for (const s of trace.steps) {
      state = ui.step(state, s.event as ui.UiEvent);
      expect(s.state).toBe(state);
    }
    expect(timeline.state).toBe("idle");
    expect(timeline.pct).toBe(0);
  });

  it("advances only while playing", () => {
    const { timeline } = make();
    timeline.advance(1);
    expect(timeline.pct).toBe(0);
    timeline.play();
    timeline.advance(timeline.duration / 4);
    expect(timeline.pct).toBeCloseTo(25, 6);
    timeline.setSpeed(0.25);
    timeline.advance(timeline.duration / 4);
    expect(timeline.pct).toBeCloseTo(31.25, 6);
    timeline.pause();
    timeline.advance(1);
    expect(timeline.pct).toBeCloseTo(31.25, 6);
  });

  it("loops at the end and stops without loop", () => {
    const a = make(true).timeline;
    a.play();
    a.advance(a.duration * 1.1);
    expect(a.state).toBe("playing");
    expect(a.pct).toBeCloseTo(10, 6);
    const b = make(false).timeline;
    b.play();
    b.advance(b.duration * 1.1);
    expect(b.state).toBe("paused");
    expect(b.pct).toBe(100);
    b.play();
    expect(b.pct).toBe(0);
  });

  it("selection follows selectNode and closeInspector; a scrub ignores clicks", () => {
    const { timeline } = make();
    const seen: (string | null)[] = [];
    timeline.onSelect((id) => seen.push(id));
    timeline.play();
    timeline.select("muscle:vaslat_r");
    expect(timeline.state).toBe("inspectingNode");
    expect(timeline.selectedId).toBe("muscle:vaslat_r");
    timeline.advance(1);
    expect(timeline.pct).toBe(0); // holds still while inspecting
    timeline.closeInspector();
    expect(timeline.state).toBe("paused");
    expect(seen).toEqual(["muscle:vaslat_r", null]);
    timeline.scrubStart();
    timeline.select("muscle:recfem_r");
    expect(timeline.selectedId).toBeNull();
  });

  it("announces phase changes", () => {
    const { timeline } = make();
    const seen: string[] = [];
    timeline.onPhase((b) => seen.push(b.id));
    timeline.scrubStart();
    timeline.scrubTo(45);
    timeline.scrubTo(47);
    timeline.scrubTo(70);
    expect(seen).toEqual(["phase:terminalStance", "phase:initialSwing"]);
  });
});

describe("Timeline gait events", () => {
  it("play through one stride records STRIDE_WORD, closing on initial contact when it wraps", () => {
    const { recorder, timeline } = make(true);
    timeline.play();
    const dt = timeline.duration / 1000;
    for (let i = 0; i < 1001; i++) timeline.advance(dt);
    const trace = recorder.toJSON().traces.find((t) => t.machine === "gait")!;
    expect(trace.steps.map((s) => s.event)).toEqual([...gait.STRIDE_WORD]);
    let g: gait.GaitPhase = gait.START;
    for (const s of trace.steps) {
      g = gait.step(g, s.event as gait.GaitEvent);
      expect(s.state).toBe(g);
    }
    expect(g).toBe("loadingResponse");
    expect(timeline.gaitState).toBe("loadingResponse");
  });

  it("a scrub into the middle leaves the gait trace until the next initial contact", () => {
    const { recorder, timeline } = make(true);
    timeline.scrubStart();
    timeline.scrubTo(60);
    timeline.scrubEnd();
    expect(timeline.gaitState).toBeNull();
    timeline.play();
    timeline.advance(timeline.duration * 0.6); // wraps to 20 %
    expect(timeline.gaitState).toBe("midStance");
    const traces = recorder.toJSON().traces.filter((t) => t.machine === "gait");
    expect(traces.at(-1)?.steps.map((s) => s.event)).toEqual(["oppositeToeOff"]);
  });
});
