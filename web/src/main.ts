import { GRAPH } from "./config";
import { GraphStore } from "./store/GraphStore";
import { QueryEngine } from "./query/QueryEngine";
import { GraphView } from "./graphview/GraphView";

/** App: wires store, query, and view; the search box focuses a node. */
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
search.addEventListener("input", () => {
  const found = query.search(search.value)[0];
  if (found) view.focus(found.id);
});
