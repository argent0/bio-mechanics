"""Text drawing of the module map, as lines plus highlight spans.

`render` is a pure function from the map, a detail level and an optional selected
module to a `Rendered`: the lines to show and the spans to highlight. The same
function feeds `print` (spans ignored) and the `watch` terminal UI.

Detail 0 lists module ids per layer and one line per API (as `lake exe arch print`
does). Details 1-3 draw boxes (see `content.box_lines`) joined by arrows: each API has
a lane in the gap below its producer; `▼` marks each arrival above a consumer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.arch.content import api_line, box_lines
from tools.arch.layout import Layout, make_layout
from tools.arch.model import ArchMap
from tools.arch.route import Route, route_edges

# Styles of highlight spans.
SELECTED = "selected"
RELATED = "related"
EDGE = "edge"

_UP, _DOWN, _LEFT, _RIGHT = 1, 2, 4, 8
_LINE_CHARS = {
    0: " ", _UP: "│", _DOWN: "│", _UP | _DOWN: "│", _LEFT: "─", _RIGHT: "─",
    _LEFT | _RIGHT: "─", _UP | _LEFT: "┘", _UP | _RIGHT: "└", _DOWN | _LEFT: "┐",
    _DOWN | _RIGHT: "┌", _UP | _DOWN | _LEFT: "┤", _UP | _DOWN | _RIGHT: "├",
    _UP | _LEFT | _RIGHT: "┴", _DOWN | _LEFT | _RIGHT: "┬", 15: "┼",
}


@dataclass(frozen=True)
class Span:
    """Cells `[start, end)` of line `line` drawn in `style`."""

    line: int
    start: int
    end: int
    style: str


@dataclass(frozen=True)
class Rect:
    y: int
    x: int
    h: int
    w: int


@dataclass
class Rendered:
    """Lines of the drawing, highlight spans, and the rectangle of each module."""

    lines: list[str]
    spans: list[Span] = field(default_factory=list)
    boxes: dict[str, Rect] = field(default_factory=dict)


def _ports(count: int, x0: int, width: int) -> list[int]:
    """Distinct interior columns of a box of outer width `width` at column `x0`."""
    return [x0 + 1 + (i + 1) * (width - 2) // (count + 1) for i in range(count)]


class _Grid:
    """Character grid: literal text on top of merged line segments."""

    def __init__(self) -> None:
        self.text: dict[tuple[int, int], str] = {}
        self.mask: dict[tuple[int, int], int] = {}
        self.tags: dict[tuple[int, int], set[int]] = {}

    def put(self, y: int, x: int, s: str, tag: int | None = None) -> None:
        for i, ch in enumerate(s):
            self.text[(y, x + i)] = ch
            if tag is not None:
                self.tags.setdefault((y, x + i), set()).add(tag)

    def line(self, pts: tuple[tuple[int, int], ...], tag: int) -> None:
        """Draw the orthogonal polyline through `(x, y)` points."""
        for (xa, ya), (xb, yb) in zip(pts, pts[1:], strict=False):
            if xa == xb:
                lo, hi = sorted((ya, yb))
                for y in range(lo, hi + 1):
                    bits = (_DOWN if y < hi else 0) | (_UP if y > lo else 0)
                    self._add(y, xa, bits, tag)
            else:
                lo, hi = sorted((xa, xb))
                for x in range(lo, hi + 1):
                    bits = (_RIGHT if x < hi else 0) | (_LEFT if x > lo else 0)
                    self._add(ya, x, bits, tag)

    def _add(self, y: int, x: int, bits: int, tag: int) -> None:
        self.mask[(y, x)] = self.mask.get((y, x), 0) | bits
        self.tags.setdefault((y, x), set()).add(tag)

    def char(self, y: int, x: int) -> str:
        if (y, x) in self.text:
            return self.text[(y, x)]
        return _LINE_CHARS[self.mask.get((y, x), 0)]


class _Geo:
    """Cell coordinates of ports, lanes and gutters (implements `route.Geometry`)."""

    def __init__(self, arch: ArchMap, layout: Layout, widths: dict[str, int],
                 xs: dict[str, int], row_top: list[int], row_h: list[int],
                 gap_top: list[int], heights: dict[str, int]) -> None:
        self.arch, self.layout, self.widths, self.xs = arch, layout, widths, xs
        self.heights = heights
        self.row_top, self.row_h, self.gap_top = row_top, row_h, gap_top

    def out_x(self, module: str, api: str) -> float:
        m = self.arch.module(module)
        cols = _ports(len(m.produces), self.xs[module], self.widths[module])
        return cols[m.produces.index(api)]

    def in_x(self, module: str, api: str) -> float:
        m = self.arch.module(module)
        cols = _ports(len(m.consumes), self.xs[module], self.widths[module])
        return cols[m.consumes.index(api)]

    def start_y(self, module: str) -> float:
        return self.row_top[self.layout.row_of[module]] + self.heights[module]

    def arrive_y(self, row: int) -> float:
        return self.row_top[row] - 1

    def lane_y(self, gap: int, api: str) -> float:
        return self.gap_top[gap] + 1 + self.layout.lanes[gap].index(api)

    def gutter_x(self, api: str) -> float:
        return 2 * self.layout.gutters.index(api)


def _legend(arch: ArchMap, detail: int) -> list[str]:
    return ["", "APIs:"] + [api_line(arch, a.id, detail) for a in arch.apis]


def _related(arch: ArchMap, selected: str) -> tuple[set[str], set[str]]:
    """Ids of the modules at the other ends of `selected`'s APIs, and those APIs."""
    others: set[str] = set()
    apis: set[str] = set()
    for a in arch.apis:
        if a.producer == selected:
            others.update(a.consumers)
            apis.add(a.id)
        elif selected in a.consumers:
            others.add(a.producer)
            apis.add(a.id)
    return others, apis


def _runs(cells: list[tuple[int, int, str]]) -> list[Span]:
    """Join horizontally adjacent cells of one style into spans."""
    spans: list[Span] = []
    for y, x, style in sorted(cells):
        last = spans[-1] if spans else None
        if last and last.line == y and last.end == x and last.style == style:
            spans[-1] = Span(y, last.start, x + 1, style)
        else:
            spans.append(Span(y, x, x + 1, style))
    return spans


def _render_names(arch: ArchMap, layout: Layout, selected: str | None) -> Rendered:
    lines: list[str] = []
    boxes: dict[str, Rect] = {}
    for r, row in enumerate(layout.rows):
        if r:
            lines.append("  ↓")
        x = 0
        for m in row:
            boxes[m] = Rect(len(lines), x, 1, len(m))
            x += len(m) + 2
        lines.append("  ".join(row))
    out = Rendered(lines + _legend(arch, 0), [], boxes)
    if selected:
        others, apis = _related(arch, selected)
        for m, rect in boxes.items():
            if m == selected or m in others:
                out.spans.append(Span(rect.y, rect.x, rect.x + rect.w,
                                      SELECTED if m == selected else RELATED))
        for i, a in enumerate(arch.apis):
            if a.id in apis:
                text = out.lines[len(lines) + 2 + i]
                out.spans.append(Span(len(lines) + 2 + i, 0, len(text), EDGE))
    return out


def render(arch: ArchMap, detail: int, selected: str | None = None) -> Rendered:
    """Draw the map at `detail` 0-3; `selected` is a module id to highlight, or None."""
    detail = max(0, min(3, detail))
    layout = make_layout(arch)
    if detail == 0:
        return _render_names(arch, layout, selected)
    bodies = {m.id: box_lines(m, detail) for m in arch.modules}
    widths: dict[str, int] = {}
    for m in arch.modules:
        ports = max(len(m.produces), len(m.consumes))
        widths[m.id] = max(max(len(s) for s in bodies[m.id]) + 4, 2 * ports + 3)
    heights = {k: len(v) + 2 for k, v in bodies.items()}
    margin = 2 * len(layout.gutters) + (1 if layout.gutters else 0)
    xs: dict[str, int] = {}
    for row in layout.rows:
        x = margin
        for mid in row:
            xs[mid] = x
            x += widths[mid] + 2
    row_h = [max(heights[m] for m in row) for row in layout.rows]
    row_top: list[int] = []
    gap_top: list[int] = []
    y = 0
    for r, h in enumerate(row_h):
        row_top.append(y)
        y += h
        if r < len(layout.lanes):
            gap_top.append(y)
            y += len(layout.lanes[r]) + 2 if layout.lanes[r] else 1
    geo = _Geo(arch, layout, widths, xs, row_top, row_h, gap_top, heights)
    routes = route_edges(arch, layout, geo)
    grid = _Grid()
    for i, rt in enumerate(routes):
        grid.line(tuple((int(px), int(py)) for px, py in rt.points), i)
    boxes: dict[str, Rect] = {}
    for row_idx, row in enumerate(layout.rows):
        for mid in row:
            mod = arch.module(mid)
            top, x, w = row_top[row_idx], xs[mid], widths[mid]
            boxes[mid] = Rect(top, x, heights[mid], w)
            grid.put(top, x, "┌" + "─" * (w - 2) + "┐")
            for j, s in enumerate(bodies[mid]):
                grid.put(top + 1 + j, x, "│ " + s.ljust(w - 4) + " │")
            bottom = top + heights[mid] - 1
            grid.put(bottom, x, "└" + "─" * (w - 2) + "┘")
            for cx in _ports(len(mod.produces), x, w):
                grid.put(bottom, cx, "┬")
    for i, rt in enumerate(routes):
        end = rt.points[-1]
        grid.put(int(end[1]), int(end[0]), "▼", i)
    _label_lanes(grid, arch, layout, geo, routes)
    width = max((x for _, x in list(grid.text) + list(grid.mask)), default=-1) + 1
    height = max((y for y, _ in list(grid.text) + list(grid.mask)), default=-1) + 1
    lines = ["".join(grid.char(yy, xx) for xx in range(width)).rstrip() for yy in range(height)]
    out = Rendered(lines + _legend(arch, detail), [], boxes)
    if selected:
        _highlight(out, arch, grid, routes, selected, height)
    return out


def _label_lanes(grid: _Grid, arch: ArchMap, layout: Layout, geo: _Geo, routes: list[Route]) -> None:
    """Write each API id into a plain horizontal stretch of its lane, when one fits."""
    for gap, lane in enumerate(layout.lanes):
        for api in lane:
            y = int(geo.lane_y(gap, api))
            ids = {i for i, rt in enumerate(routes) if rt.api == api}
            need = len(api) + 2
            xs = sorted(x for (yy, x), m in grid.mask.items()
                        if yy == y and m == (_LEFT | _RIGHT) and (yy, x) not in grid.text
                        and grid.tags[(yy, x)] <= ids)
            for i in range(len(xs) - need + 1):
                if xs[i + need - 1] - xs[i] == need - 1:
                    for t in ids:
                        grid.tags.setdefault((y, xs[i] + 1), set()).add(t)
                    grid.put(y, xs[i] + 1, api)
                    for k in range(len(api)):
                        grid.tags[(y, xs[i] + 1 + k)] = set(ids)
                    break


def _highlight(out: Rendered, arch: ArchMap, grid: _Grid, routes: list[Route],
               selected: str, map_height: int) -> None:
    others, apis = _related(arch, selected)
    lit = {i for i, rt in enumerate(routes) if selected in (rt.producer, rt.consumer)}
    cells = [(y, x, EDGE) for (y, x), tg in grid.tags.items() if tg & lit]
    for mid, rect in out.boxes.items():
        if mid == selected or mid in others:
            style = SELECTED if mid == selected else RELATED
            cells = [c for c in cells if not (rect.y <= c[0] < rect.y + rect.h
                                               and rect.x <= c[1] < rect.x + rect.w)]
            cells += [(y, x, style) for y in range(rect.y, rect.y + rect.h)
                      for x in range(rect.x, rect.x + rect.w)]
    out.spans = _runs(cells)
    for i, a in enumerate(arch.apis):
        if a.id in apis:
            y = map_height + 2 + i
            out.spans.append(Span(y, 0, len(out.lines[y]), EDGE))
