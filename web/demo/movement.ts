/**
 * Demo entry of the movement views (workstream E3): the composition the App performs.
 * It stands outside `web/src/` because composing Viewer3D, PhasePanel and Timeline needs the
 * GraphStore, which the component digraph allows only to QueryEngine and App.
 */
import { GRAPH } from "../src/config";
import { GraphStore } from "../src/store/GraphStore";
import { QueryEngine } from "../src/query/QueryEngine";
import { Timeline, loadMusclePaths, mountTimeline } from "../src/timeline";
import { mountViewer3D } from "../src/viewer";
import { mountPhasePanel } from "../src/phase";

const byId = (id: string) => document.getElementById(id) as HTMLElement;
const query = new QueryEngine(new GraphStore(GRAPH));
// This page lives one directory below the site root, where Vite serves the pipeline output.
const dataBase = "../";
const clip = await loadMusclePaths(dataBase);
const timeline = new Timeline({ query, clip });
mountTimeline(byId("timeline"), timeline);
mountPhasePanel(byId("phase"), { query, timeline });
const viewer = await mountViewer3D(byId("view"), { query, timeline, dataBase });
Object.assign(window, { __bm: { timeline, viewer } });

// Query string `?t=<percent>` starts paused at a position (for screenshots).
const t = new URLSearchParams(location.search).get("t");
if (t !== null) {
  timeline.scrubStart();
  timeline.scrubTo(Number(t));
  timeline.scrubEnd();
}
