/** The one place that names the graph source: the pipeline's knowledge graph
 * (`data/out/graph.json`, written by `pipeline/export_graph.py`). Tests use the
 * hand-made fixture `data/fixtures/graph.sample.json` directly. */
import source from "../../data/out/graph.json";
import type { Graph } from "@gen/types";

export const GRAPH = source as unknown as Graph;
