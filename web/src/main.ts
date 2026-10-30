import { GRAPH } from "./config";
import { GraphStore } from "./store/GraphStore";
import { QueryEngine } from "./query/QueryEngine";
import { GraphView } from "./graphview/GraphView";
import { highlightState, mountArchitectureView } from "./architecture";
import { recorder } from "./trace";

/** App: wires store, query, and view; the search box focuses a node on Enter or on a picked suggestion. */
const query = new QueryEngine(new GraphStore(GRAPH));
const byId = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const view = new GraphView(byId("graph"), query, byId("details"));

const search = byId<HTMLInputElement>("search");
const hits = byId<HTMLDataListElement>("hits");
for (const n of query.allNodes()) {
  for (const label of [n.name, n.commonName]) {
    if (label) hits.append(Object.assign(document.createElement("option"), { value: label }));
  }
}
const select = () => {
  const found = query.search(search.value)[0];
  if (found) view.focus(found.id);
};
/** Enter selects the first match. Picking a suggestion selects it too: browsers
 * report that pick as an input event of type `insertReplacementText`, or as a
 * plain `Event`, while typed keys arrive as other `InputEvent` types. */
search.addEventListener("keydown", (ev) => { if (ev.key === "Enter") select(); });
search.addEventListener("input", (ev) => {
  if (!(ev instanceof InputEvent) || ev.inputType === "insertReplacementText") select();
});

/** Movement view (`#/walking`): Timeline, Viewer3D, PhasePanel and DynamicsPanel over the
 * pipeline's walking clip. The viewer (and three.js) loads on first visit, in its own chunk. */
async function mountWalking(): Promise<void> {
  const [{ Timeline, loadMusclePaths, mountTimeline }, { mountPhasePanel, mountDynamicsPanel, loadDynamics }, { mountViewer3D }] =
    await Promise.all([import("./timeline"), import("./phase"), import("./viewer")]);
  const [clip, dynamics] = await Promise.all([loadMusclePaths("./"), loadDynamics("./")]);
  const timeline = new Timeline({ query, clip });
  mountTimeline(byId("walk-timeline"), timeline);
  mountPhasePanel(byId("walk-phase"), { query, timeline });
  mountDynamicsPanel(byId("walk-dynamics"), { query, timeline, clip, dynamics });
  await mountViewer3D(byId("walk-view"), { query, timeline, dataBase: "./" });
}

/** In dev mode, every recorded FSM step lights the matching state on the architecture page. */
recorder.onStep((machine, _step, state) => highlightState(machine === "gait" ? "gaitFsm" : "uiFsm", state));

/** Routes: `#/walking` shows the movement view and `#/architecture` the ArchitectureView,
 * each mounted on first visit; any other hash shows the graph explorer. */
const views = { explore: "", walking: "#/walking", arch: "#/architecture" } as const;
const mounted = new Set<string>();
const route = () => {
  const active = (Object.keys(views) as (keyof typeof views)[]).find((id) => views[id] === location.hash) ?? "explore";
  for (const id of Object.keys(views)) byId(id).hidden = id !== active;
  if (mounted.has(active)) return;
  mounted.add(active);
  if (active === "arch") mountArchitectureView(byId("arch"));
  if (active === "walking") void mountWalking();
};
window.addEventListener("hashchange", route);
route();
