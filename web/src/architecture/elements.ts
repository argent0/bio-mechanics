import type { ElementDefinition } from "cytoscape";
import type { Architecture, DiagramId, Fsm, Loc } from "./types";

const doc = (d: string | null) => d ?? "";

/** Plain-language labels for the audience, beside the formal names. */
export const PLAIN: Record<DiagramId, { title: string; blurb: string }> = {
  schema: { title: "Body graph schema", blurb: "The kinds of things in the body graph (bones, muscles, joints...) and how they connect." },
  gaitFsm: { title: "Walking cycle", blurb: "The phases of one walking stride and the events that move from one phase to the next." },
  uiFsm: { title: "App modes", blurb: "The screens and modes the explorer moves through as you use it." },
  pipeline: { title: "Data pipeline", blurb: "The processing steps that turn motion data into the numbers shown in the app." },
  components: { title: "App building blocks", blurb: "The parts of the web app and which part may use which." },
};

export const DIAGRAMS: DiagramId[] = ["schema", "gaitFsm", "uiFsm", "pipeline", "components"];

function node(id: string, label: string, d: string | null, loc: Loc | null, extra: Record<string, unknown> = {}, classes = ""): ElementDefinition {
  return { group: "nodes", data: { id, label, doc: doc(d), loc, ...extra }, classes };
}
function edge(id: string, source: string, target: string, label: string, loc: Loc | null = null): ElementDefinition {
  return { group: "edges", data: { id, source, target, label, doc: "", loc } };
}

export function schemaElements(a: Architecture): ElementDefinition[] {
  const s = a.schema;
  return [
    ...s.kinds.map((k) => node(k.name, k.name, k.doc, s.loc)),
    ...s.arrows.map((r, i) => edge(`arrow${i}:${r.name}`, r.source, r.target, r.name, s.loc)),
  ];
}

/** Transitions between the same two states merge into one edge labelled with all events. */
export function fsmElements(f: Fsm): ElementDefinition[] {
  const nodes = f.states.map((s) => {
    const cls = [s.name === f.start ? "start" : "", f.accept.includes(s.name) ? "accept" : "",
      f.implicit.kind !== "selfLoop" && s.name === f.implicit.state ? "sink faded" : ""].filter(Boolean).join(" ");
    return node(`${f.id}:${s.name}`, s.name, s.doc, f.loc, { state: s.name }, cls);
  });
  const merged = new Map<string, { from: string; to: string; events: string[] }>();
  for (const t of f.transitions) {
    const k = `${t.from}->${t.to}`;
    const m = merged.get(k) ?? { from: t.from, to: t.to, events: [] };
    m.events.push(t.event);
    merged.set(k, m);
  }
  const edges = [...merged.values()].map((m) =>
    edge(`${f.id}:${m.from}->${m.to}`, `${f.id}:${m.from}`, `${f.id}:${m.to}`, m.events.join(", "), f.loc));
  return [...nodes, ...edges];
}

export function pipelineElements(a: Architecture): ElementDefinition[] {
  const p = a.pipeline;
  const byName = new Map(p.stages.map((s) => [s.name, s]));
  const nodes = p.topoOrder.map((n) => {
    const s = byName.get(n);
    return node(n, n, s?.doc ?? null, p.loc, { script: s?.script ?? "" });
  });
  return [...nodes, ...p.edges.map((e) => edge(`${e.source}->${e.target}`, e.source, e.target, e.artefacts.join(", "), p.loc))];
}

export function componentElements(a: Architecture): ElementDefinition[] {
  const c = a.components;
  const byName = new Map(c.components.map((x) => [x.name, x]));
  const nodes = c.topoOrder.map((n) => {
    const x = byName.get(n);
    const paths = x?.paths ?? [];
    return node(n, paths.length ? `${n}\n${paths.join("\n")}` : n, x?.doc ?? null, c.loc, { paths });
  });
  return [...nodes, ...c.edges.map((e) => edge(`${e.source}->${e.target}`, e.source, e.target, "", c.loc))];
}

export function elementsFor(a: Architecture, d: DiagramId): ElementDefinition[] {
  switch (d) {
    case "schema": return schemaElements(a);
    case "gaitFsm": case "uiFsm": return fsmElements(a.fsms.find((f) => f.id === d) as Fsm);
    case "pipeline": return pipelineElements(a);
    case "components": return componentElements(a);
  }
}

/** Lean module behind a diagram; the theorem panel filters on it. */
export function moduleOf(a: Architecture, d: DiagramId): string {
  switch (d) {
    case "schema": return a.schema.loc.module;
    case "gaitFsm": case "uiFsm": return (a.fsms.find((f) => f.id === d) as Fsm).module;
    case "pipeline": return a.pipeline.loc.module;
    case "components": return a.components.loc.module;
  }
}

export function diagramLoc(a: Architecture, d: DiagramId): Loc {
  switch (d) {
    case "schema": return a.schema.loc;
    case "gaitFsm": case "uiFsm": return (a.fsms.find((f) => f.id === d) as Fsm).loc;
    case "pipeline": return a.pipeline.loc;
    case "components": return a.components.loc;
  }
}

export function theoremsFor(a: Architecture, module: string | null) {
  return module === null ? a.theorems : a.theorems.filter((t) => t.loc.module === module);
}
