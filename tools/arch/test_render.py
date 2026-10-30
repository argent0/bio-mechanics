"""Text and SVG drawings over the real module map."""

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.arch.model import ArchMap, load_map
from tools.arch.svg import render_svg
from tools.arch.text import EDGE, RELATED, SELECTED, render

ROOT = Path(__file__).resolve().parents[2]
REAL_MAP = ROOT / "generated" / "modules.json"


@pytest.fixture(scope="module")
def arch() -> ArchMap:
    return load_map(REAL_MAP)


@pytest.mark.parametrize("detail", range(4))
def test_every_module_and_api_drawn(arch: ArchMap, detail: int) -> None:
    text = "\n".join(render(arch, detail).lines)
    for m in arch.modules:
        assert m.id in text and (detail == 0 or m.name in text)
    for a in arch.apis:
        assert f"{a.id} {a.name} ─ {a.producer} → {', '.join(a.consumers)}" in text


def test_detail_levels_add_content(arch: ArchMap) -> None:
    d = ["\n".join(render(arch, n).lines) for n in range(4)]
    h = arch.module("H")
    head = f"{h.lang} · {h.model} · {h.state}"
    assert "┌" not in d[0]
    assert f"out: {', '.join(h.produces) or '-'}" in d[1] and head not in d[1]
    assert f"in:  {', '.join(h.consumes)}" in d[1]
    assert head in d[2] and f"• {h.paths[0]}" not in d[2]
    assert f"• {h.paths[0]}" in d[3] and f"$ {h.acceptance[0]}" in d[3]
    for api in arch.apis:
        assert f"[{', '.join(api.files)}]" in d[3]


def test_detail_zero_matches_lean_rows(arch: ArchMap) -> None:
    lines = render(arch, 0).lines
    top = {m.id for m in arch.modules if m.layer == min(x.layer for x in arch.modules)}
    assert set(lines[0].split()) == top
    assert lines[1] == "  ↓"


def test_arrows_connect_every_consumer(arch: ArchMap) -> None:
    text = "\n".join(render(arch, 1).lines)
    arrivals = sum(len(a.consumers) for a in arch.apis)
    assert text.count("▼") == arrivals


def test_selection_spans(arch: ArchMap) -> None:
    sel = next(m for m in arch.modules if m.produces and m.consumes)
    others = {c for a in arch.apis if a.producer == sel.id for c in a.consumers}
    others |= {a.producer for a in arch.apis if sel.id in a.consumers}
    r = render(arch, 1, sel.id)
    styles = {s.style for s in r.spans}
    assert {SELECTED, RELATED, EDGE} <= styles
    selected = [s for s in r.spans if s.style == SELECTED]
    box = r.boxes[sel.id]
    assert {s.line for s in selected} == set(range(box.y, box.y + box.h))
    related_lines = {s.line for s in r.spans if s.style == RELATED}
    for other in others:
        assert r.boxes[other].y + 1 in related_lines
    assert all(r.lines[s.line][s.start : s.end] for s in r.spans)
    assert render(arch, 1).spans == []


def test_svg_well_formed(arch: ArchMap) -> None:
    for detail in range(4):
        root = ET.fromstring(render_svg(arch, detail))
        assert root.tag.endswith("svg")
        ns = {"s": "http://www.w3.org/2000/svg"}
        assert len(root.findall(".//s:g[@class='module']", ns)) == len(arch.modules)
        assert len(root.findall(".//s:g[@class='edge']", ns)) == sum(len(a.consumers) for a in arch.apis)
    states = {g.get("data-state") for g in root.findall(".//{http://www.w3.org/2000/svg}g[@class='module']")}
    assert states == {m.state for m in arch.modules}


def test_cli(tmp_path: Path) -> None:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "tools.arch", *args], cwd=ROOT,
                              capture_output=True, text=True, check=False)

    for n in range(4):
        out = run("print", "--detail", str(n))
        assert out.returncode == 0 and "APIs:" in out.stdout
    svg = tmp_path / "a.svg"
    assert run("svg", "-o", str(svg), "--map", str(REAL_MAP)).returncode == 0
    ET.parse(svg)
    bad = run("print", "--map", str(tmp_path / "none.json"))
    assert bad.returncode == 2 and "cannot read" in bad.stderr
