"""Compare two `graph.json` files: structure exactly, numbers within a tolerance.

Usage: python scripts/compare_graph.py COMMITTED REGENERATED [--tol 0.02]

Static optimisation is a numerical solver, so a pipeline run on another machine
reproduces the committed graph up to floating-point drift. This script holds
the regenerated graph to the committed one:

* exactly: the node set (every node field), and per edge its source, target,
  relation, and every string or integer attribute (phase, role, contraction,
  order, coordinate);
* within `--tol` (absolute): every float attribute, element by element for
  sample lists of equal length.

Exit 0 when they agree, 1 with the differences listed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

Json = object


def edge_key(edge: dict[str, Json]) -> tuple[str, ...]:
    return tuple(str(edge.get(k)) for k in ("source", "relation", "target", "phase"))


def close(a: Json, b: Json, tol: float) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tol
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    return a == b


def differences(old: dict[str, Json], new: dict[str, Json], tol: float) -> list[str]:
    out: list[str] = []
    old_nodes = old["nodes"]
    new_nodes = new["nodes"]
    assert isinstance(old_nodes, list) and isinstance(new_nodes, list)
    if sorted(json.dumps(n, sort_keys=True) for n in old_nodes) != sorted(
        json.dumps(n, sort_keys=True) for n in new_nodes
    ):
        out.append("nodes differ")
    old_edges = old["edges"]
    new_edges = new["edges"]
    assert isinstance(old_edges, list) and isinstance(new_edges, list)
    olds = {edge_key(e): e for e in old_edges}
    news = {edge_key(e): e for e in new_edges}
    for key in sorted(olds.keys() - news.keys()):
        out.append(f"edge only in committed: {key}")
    for key in sorted(news.keys() - olds.keys()):
        out.append(f"edge only in regenerated: {key}")
    for key in sorted(olds.keys() & news.keys()):
        a, b = olds[key], news[key]
        for field in sorted(set(a) | set(b)):
            if not close(a.get(field), b.get(field), tol):
                out.append(f"edge {key}: field {field} differs beyond {tol}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("committed", type=Path)
    parser.add_argument("regenerated", type=Path)
    parser.add_argument("--tol", type=float, default=0.02)
    args = parser.parse_args()
    old = json.loads(args.committed.read_text())
    new = json.loads(args.regenerated.read_text())
    diffs = differences(old, new, args.tol)
    for line in diffs:
        print(line)
    print(f"compare_graph: {len(diffs)} difference(s)")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
