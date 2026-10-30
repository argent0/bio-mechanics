/** The one place that names the graph source. Swap to
 * `../../data/out/graph.json` when the pipeline output replaces the fixture. */
import source from "../../data/fixtures/graph.sample.json";
import type { Graph } from "@gen/types";

export const GRAPH = source as unknown as Graph;
