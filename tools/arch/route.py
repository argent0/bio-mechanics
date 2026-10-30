"""Orthogonal edge routes shared by the text and SVG drawings.

A route runs from the producer's bottom port down into the API's lane in the gap
below the producer's row, then sideways. A consumer in the next row is reached by
moving along the lane to the consumer's top port and dropping. A consumer further
down is reached through the API's gutter, a column left of all boxes, which leads to
the API's lane in the gap above the consumer's row, then along it to the top port.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tools.arch.layout import Layout
from tools.arch.model import ArchMap

Point = tuple[float, float]


class Geometry(Protocol):
    """Coordinates the drawing medium supplies (text cells or SVG pixels)."""

    def out_x(self, module: str, api: str) -> float: ...
    def in_x(self, module: str, api: str) -> float: ...
    def start_y(self, module: str) -> float:
        """Where a route leaves `module` (just below its box)."""
        ...
    def arrive_y(self, row: int) -> float:
        """Where a route ends above row `row` (just above its boxes)."""
        ...
    def lane_y(self, gap: int, api: str) -> float: ...
    def gutter_x(self, api: str) -> float: ...


@dataclass(frozen=True)
class Route:
    api: str
    producer: str
    consumer: str
    points: tuple[Point, ...]


def route_edges(arch: ArchMap, layout: Layout, geo: Geometry) -> list[Route]:
    """One route per (API, consumer), in the order of `arch.apis`."""
    routes: list[Route] = []
    for a in arch.apis:
        top = layout.row_of[a.producer]
        x0 = geo.out_x(a.producer, a.id)
        for c in a.consumers:
            row = layout.row_of[c]
            x1 = geo.in_x(c, a.id)
            pts: list[Point] = [(x0, geo.start_y(a.producer)), (x0, geo.lane_y(top, a.id))]
            if row == top + 1:
                pts.append((x1, geo.lane_y(top, a.id)))
            else:
                g = geo.gutter_x(a.id)
                pts += [(g, geo.lane_y(top, a.id)), (g, geo.lane_y(row - 1, a.id)),
                        (x1, geo.lane_y(row - 1, a.id))]
            pts.append((x1, geo.arrive_y(row)))
            clean = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
            routes.append(Route(a.id, a.producer, c, tuple(clean)))
    return routes
