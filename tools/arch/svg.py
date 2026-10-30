"""Standalone SVG drawing of the module map.

Layers are rows; boxes are ordered by barycentre (`layout.make_layout`); each API is
an orthogonal arrow from its producer to each consumer (`route.route_edges`), labelled
with the API id at the arrowhead; box colour follows the module state.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from tools.arch.content import api_line, box_lines
from tools.arch.layout import Layout, make_layout
from tools.arch.model import ArchMap
from tools.arch.route import route_edges

#: Fill and stroke per module state; unknown states use `_OTHER`.
STATE_COLOURS: dict[str, tuple[str, str]] = {
    "planned": ("#eceff1", "#78909c"),
    "running": ("#fff3cd", "#c58b00"),
    "review": ("#e8def8", "#7e57c2"),
    "merged": ("#d7f0dc", "#2e7d32"),
}
_OTHER = ("#ffffff", "#444444")
_EDGE_COLOURS = ("#1565c0", "#c62828", "#2e7d32", "#6a1b9a", "#ef6c00", "#00838f", "#ad1457", "#4e342e")

_CHAR_W = 7.2
_LINE_H = 16.0
_PAD = 8.0
_FONT = 12
_LANE_H = 16.0
_GUTTER_W = 14.0
_ROW_GAP = 20.0


def _ports(count: int, x0: float, width: float) -> list[float]:
    return [x0 + width * (i + 1) / (count + 1) for i in range(count)]


class _Geo:
    def __init__(self, arch: ArchMap, layout: Layout, xs: dict[str, float], ws: dict[str, float],
                 row_top: list[float], row_h: list[float], gap_top: list[float],
                 heights: dict[str, float]) -> None:
        self.arch, self.layout, self.xs, self.ws = arch, layout, xs, ws
        self.heights = heights
        self.row_top, self.row_h, self.gap_top = row_top, row_h, gap_top

    def out_x(self, module: str, api: str) -> float:
        m = self.arch.module(module)
        return _ports(len(m.produces), self.xs[module], self.ws[module])[m.produces.index(api)]

    def in_x(self, module: str, api: str) -> float:
        m = self.arch.module(module)
        return _ports(len(m.consumes), self.xs[module], self.ws[module])[m.consumes.index(api)]

    def start_y(self, module: str) -> float:
        return self.row_top[self.layout.row_of[module]] + self.heights[module]

    def arrive_y(self, row: int) -> float:
        return self.row_top[row]

    def lane_y(self, gap: int, api: str) -> float:
        return self.gap_top[gap] + _ROW_GAP / 2 + _LANE_H * (0.5 + self.layout.lanes[gap].index(api))

    def gutter_x(self, api: str) -> float:
        return _PAD + _GUTTER_W * (0.5 + self.layout.gutters.index(api))


def render_svg(arch: ArchMap, detail: int = 2) -> str:
    """Return the SVG document text for `arch` at `detail` 0-3."""
    detail = max(0, min(3, detail))
    layout = make_layout(arch)
    bodies = {m.id: box_lines(m, detail) for m in arch.modules}
    heights = {k: len(v) * _LINE_H + 2 * _PAD for k, v in bodies.items()}
    ws: dict[str, float] = {}
    for m in arch.modules:
        ports = max(len(m.produces), len(m.consumes))
        ws[m.id] = max(max(len(s) for s in bodies[m.id]) * _CHAR_W + 2 * _PAD + 4, 28.0 * (ports + 1))
    margin = _PAD + _GUTTER_W * len(layout.gutters)
    xs: dict[str, float] = {}
    total_w = margin
    for row in layout.rows:
        x = margin
        for mid in row:
            xs[mid] = x
            x += ws[mid] + 24
        total_w = max(total_w, x - 24)
    row_h = [max(heights[m] for m in row) for row in layout.rows]
    row_top: list[float] = []
    gap_top: list[float] = []
    y = _PAD
    for r, h in enumerate(row_h):
        row_top.append(y)
        y += h
        if r < len(layout.lanes):
            gap_top.append(y)
            y += _ROW_GAP + _LANE_H * len(layout.lanes[r])
    legend_top = y + 24
    legend = [api_line(arch, a.id, detail) for a in arch.apis]
    legend_w = max((len(s) for s in legend), default=0) * _CHAR_W + 2 * _PAD
    width = max(total_w, legend_w) + _PAD
    height = legend_top + _LINE_H * (len(legend) + 2) + _PAD
    geo = _Geo(arch, layout, xs, ws, row_top, row_h, gap_top, heights)
    colour = {a.id: _EDGE_COLOURS[i % len(_EDGE_COLOURS)] for i, a in enumerate(arch.apis)}
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="monospace" font-size="{_FONT}">',
        "<title>Bio-Mechanics module map</title>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        "<defs>" + "".join(
            f'<marker id="arrow-{a.id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{colour[a.id]}"/></marker>'
            for a in arch.apis) + "</defs>",
    ]
    for rt in route_edges(arch, layout, geo):
        d = " ".join(f"{'M' if i == 0 else 'L'}{px:.1f} {py:.1f}" for i, (px, py) in enumerate(rt.points))
        api = arch.api(rt.api)
        ex, ey = rt.points[-1]
        out.append(
            f'<g class="edge" data-api={quoteattr(rt.api)} data-from={quoteattr(rt.producer)} '
            f'data-to={quoteattr(rt.consumer)}><title>{escape(rt.api)} {escape(api.name)}: '
            f'{escape(rt.producer)} to {escape(rt.consumer)}</title>'
            f'<path d="{d}" fill="none" stroke="{colour[rt.api]}" stroke-width="1.5" '
            f'marker-end="url(#arrow-{rt.api})"/>'
            f'<text x="{ex + 4:.1f}" y="{ey - 6:.1f}" fill="{colour[rt.api]}" font-weight="bold" '
            f'font-size="11">{escape(rt.api)}</text></g>')
    for m in arch.modules:
        fill, stroke = STATE_COLOURS.get(m.state, _OTHER)
        x, top = xs[m.id], row_top[layout.row_of[m.id]]
        out.append(f'<g class="module" data-id={quoteattr(m.id)} data-state={quoteattr(m.state)}>'
                   f'<rect x="{x:.1f}" y="{top:.1f}" width="{ws[m.id]:.1f}" height="{heights[m.id]:.1f}" '
                   f'rx="5" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        for i, s in enumerate(bodies[m.id]):
            weight = ' font-weight="bold"' if i == 0 else ""
            out.append(f'<text x="{x + _PAD:.1f}" y="{top + _PAD + _LINE_H * (i + 0.75):.1f}" '
                       f'fill="#222222"{weight} xml:space="preserve">{escape(s)}</text>')
        out.append("</g>")
    out.append(f'<text x="{_PAD}" y="{legend_top:.1f}" font-weight="bold" fill="#222222">APIs</text>')
    for i, s in enumerate(legend):
        out.append(f'<text x="{_PAD}" y="{legend_top + _LINE_H * (i + 1):.1f}" fill="{colour[arch.apis[i].id]}" '
                   f'xml:space="preserve">{escape(s)}</text>')
    sx = _PAD
    sy = legend_top + _LINE_H * (len(legend) + 1.5)
    for state, (fill, stroke) in STATE_COLOURS.items():
        out.append(f'<rect x="{sx:.1f}" y="{sy - 10:.1f}" width="12" height="12" rx="2" fill="{fill}" '
                   f'stroke="{stroke}"/><text x="{sx + 16:.1f}" y="{sy:.1f}" fill="#222222">{state}</text>')
        sx += 24 + len(state) * _CHAR_W + 12
    out.append("</svg>")
    return "\n".join(out) + "\n"
