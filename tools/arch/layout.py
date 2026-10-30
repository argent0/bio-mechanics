"""Layered layout: rows of modules, box order by barycentre, lanes and gutters."""

from __future__ import annotations

from dataclasses import dataclass

from tools.arch.model import ArchMap

_SWEEPS = 6


@dataclass(frozen=True)
class Layout:
    """Where each module and API sits in the drawing, independent of the medium.

    * `rows[r]` lists the module ids of row `r` from left to right (row 0 is the top).
    * `lanes[k]` lists the API ids that own a lane in the gap between rows `k` and
      `k+1`, from top to bottom: an API has a lane where it leaves its producer's row
      and where it arrives at a consumer's row.
    * `gutters` lists the API ids that skip a row; each owns a vertical column left of
      the boxes, from left to right.
    """

    rows: tuple[tuple[str, ...], ...]
    row_of: dict[str, int]
    lanes: tuple[tuple[str, ...], ...]
    gutters: tuple[str, ...]


def _rank(arch: ArchMap) -> dict[str, int]:
    """Row index of each module: the rank of its layer among the layers in use."""
    layers = sorted({m.layer for m in arch.modules})
    index = {layer: i for i, layer in enumerate(layers)}
    return {m.id: index[m.layer] for m in arch.modules}


def _neighbours(arch: ArchMap) -> dict[str, list[str]]:
    near: dict[str, list[str]] = {m.id: [] for m in arch.modules}
    for a in arch.apis:
        for c in a.consumers:
            near[a.producer].append(c)
            near[c].append(a.producer)
    return near


def _crossings(arch: ArchMap, rows: list[list[str]], row_of: dict[str, int]) -> int:
    pos = {m: i for row in rows for i, m in enumerate(row)}
    edges = [(a.producer, c) for a in arch.apis for c in a.consumers]
    total = 0
    for i, (p1, c1) in enumerate(edges):
        for p2, c2 in edges[i + 1 :]:
            if row_of[p1] != row_of[p2] or row_of[c1] != row_of[c2]:
                continue
            if (pos[p1] - pos[p2]) * (pos[c1] - pos[c2]) < 0:
                total += 1
    return total


def _sweep(rows: list[list[str]], near: dict[str, list[str]], order: range, toward: int) -> None:
    """Reorder rows in `order` by the mean position of neighbours in rows before them."""
    for r in order:
        pos = {m: (i + 0.5) / len(rows[q]) for q in range(len(rows)) for i, m in enumerate(rows[q])}
        row_of = {m: q for q in range(len(rows)) for m in rows[q]}
        keyed: list[tuple[float, int, str]] = []
        for i, m in enumerate(rows[r]):
            ns = [n for n in near[m] if (row_of[n] - r) * toward < 0]
            bary = sum(pos[n] for n in ns) / len(ns) if ns else pos[m]
            keyed.append((bary, i, m))
        rows[r] = [m for _, _, m in sorted(keyed)]


def make_layout(arch: ArchMap) -> Layout:
    """Order boxes with barycentre sweeps (keeping the order with fewest crossings)."""
    row_of = _rank(arch)
    depth = max(row_of.values(), default=-1) + 1
    rows: list[list[str]] = [[] for _ in range(depth)]
    for m in arch.modules:
        rows[row_of[m.id]].append(m.id)
    near = _neighbours(arch)
    best = [list(r) for r in rows]
    best_cost = _crossings(arch, rows, row_of)
    for _ in range(_SWEEPS):
        _sweep(rows, near, range(1, depth), 1)
        _sweep(rows, near, range(depth - 2, -1, -1), -1)
        cost = _crossings(arch, rows, row_of)
        if cost < best_cost:
            best, best_cost = [list(r) for r in rows], cost
    pos = {m: i for row in best for i, m in enumerate(row)}
    lanes: list[list[str]] = [[] for _ in range(max(depth - 1, 0))]
    gutters: list[str] = []
    for a in arch.apis:
        top = row_of[a.producer]
        reach = {row_of[c] for c in a.consumers}
        if top < depth - 1:
            lanes[top].append(a.id)
        for r in reach:
            if r - 1 != top and a.id not in lanes[r - 1]:
                lanes[r - 1].append(a.id)
        if any(r - 1 != top for r in reach):
            gutters.append(a.id)
    producer = {a.id: a.producer for a in arch.apis}
    for lane in lanes:
        lane.sort(key=lambda api: (pos[producer[api]], api))
    return Layout(
        rows=tuple(tuple(r) for r in best),
        row_of=row_of,
        lanes=tuple(tuple(lane) for lane in lanes),
        gutters=tuple(gutters),
    )
