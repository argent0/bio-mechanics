"""Compare two `graph.json` files: structure exactly, numbers within a tolerance.

Usage: python scripts/compare_graph.py COMMITTED REGENERATED [--tol 0.02] [--rel 0.05] [--max-edge-frac 0.05]
       [--within-committed]

Inverse kinematics and static optimisation are numerical solvers, so a pipeline
run on another machine reproduces the committed graph up to solver drift, and a
muscle sitting at a role threshold (D-002, D-006) may flip. This script holds
the regenerated graph to the committed one:

* exactly: the node set (every node field);
* per edge (keyed by source, relation, target, phase, coordinate): string and integer
  attributes (role, contraction, order, coordinate) exactly, and float
  attributes within `--tol` absolute or `--rel` relative, element by element
  for sample lists of equal length;
* edges present in one graph only, and edges whose attributes differ, count as
  differing edges; at most `--max-edge-frac` of the committed edges may differ.

With `--within-committed`, the regenerated graph is first cut down to the
committed graph's node ids and the edges between them (`restrict`). A graph that
grows (the left leg, the trunk and the arms, plan.md principle 6) then passes
when the part the committed graph covers holds still.

The teaching facts (e.g. the vasti braking knee flexion in loading response)
are held exactly by the pipeline's env tests in `pipeline/tests/`.

Every difference is listed. Exit 0 when the node sets agree and the differing
edges stay within the fraction, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

Json = object


def edge_key(edge: dict[str, Json]) -> tuple[str, ...]:
    return tuple(str(edge.get(k)) for k in ("source", "relation", "target", "phase", "coordinate"))


def close(a: Json, b: Json, tol: float, rel: float = 0.0) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        diff = abs(float(a) - float(b))
        return diff <= tol or diff <= rel * max(abs(float(a)), abs(float(b)))
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tol, rel) for x, y in zip(a, b))
    return a == b


def restrict(graph: dict[str, Json], ids: set[str]) -> dict[str, Json]:
    """`graph` with the nodes whose id is in `ids` and the edges between them."""
    nodes = graph["nodes"]
    edges = graph["edges"]
    assert isinstance(nodes, list) and isinstance(edges, list)
    return {
        **graph,
        "nodes": [n for n in nodes if n["id"] in ids],
        "edges": [e for e in edges if e["source"] in ids and e["target"] in ids],
    }


def differences(
    old: dict[str, Json], new: dict[str, Json], tol: float, rel: float
) -> tuple[list[str], bool, set[tuple[str, ...]], int]:
    """Listed differences, whether the node sets agree, the differing edge keys,
    and the committed edge count."""
    out: list[str] = []
    old_nodes = old["nodes"]
    new_nodes = new["nodes"]
    assert isinstance(old_nodes, list) and isinstance(new_nodes, list)
    if sorted(json.dumps(n, sort_keys=True) for n in old_nodes) != sorted(
        json.dumps(n, sort_keys=True) for n in new_nodes
    ):
        out.append("nodes differ")
    nodes_agree = not out
    old_edges = old["edges"]
    new_edges = new["edges"]
    assert isinstance(old_edges, list) and isinstance(new_edges, list)
    olds = {edge_key(e): e for e in old_edges}
    news = {edge_key(e): e for e in new_edges}
    differing: set[tuple[str, ...]] = set()
    for key in sorted(olds.keys() - news.keys()):
        out.append(f"edge only in committed: {key}")
        differing.add(key)
    for key in sorted(news.keys() - olds.keys()):
        out.append(f"edge only in regenerated: {key}")
        differing.add(key)
    for key in sorted(olds.keys() & news.keys()):
        a, b = olds[key], news[key]
        for field in sorted(set(a) | set(b)):
            if not close(a.get(field), b.get(field), tol, rel):
                out.append(f"edge {key}: field {field}: {a.get(field)!r:.60} vs {b.get(field)!r:.60}")
                differing.add(key)
    return out, nodes_agree, differing, len(olds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("committed", type=Path)
    parser.add_argument("regenerated", type=Path)
    parser.add_argument("--tol", type=float, default=0.02)
    parser.add_argument("--rel", type=float, default=0.05)
    parser.add_argument("--max-edge-frac", type=float, default=0.05)
    parser.add_argument("--within-committed", action="store_true",
                        help="compare only the committed graph's nodes and the edges between them")
    args = parser.parse_args()
    old = json.loads(args.committed.read_text())
    new = json.loads(args.regenerated.read_text())
    if args.within_committed:
        old_nodes = old["nodes"]
        assert isinstance(old_nodes, list)
        new = restrict(new, {n["id"] for n in old_nodes})
    diffs, nodes_agree, differing, total = differences(old, new, args.tol, args.rel)
    for line in diffs:
        print(line)
    frac = len(differing) / total if total else 0.0
    ok = nodes_agree and frac <= args.max_edge_frac
    print(f"compare_graph: {len(differing)} of {total} edges differ ({frac:.1%}, limit "
          f"{args.max_edge_frac:.0%}); nodes {'agree' if nodes_agree else 'differ'}: {'pass' if ok else 'fail'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
