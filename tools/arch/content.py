"""The text inside a module box, shared by the text and SVG drawings."""

from __future__ import annotations

import textwrap

from tools.arch.model import ArchMap, Module

#: Longest body line before wrapping, in characters.
WRAP = 56


def api_names(ids: tuple[str, ...]) -> str:
    return ", ".join(ids) if ids else "-"


def _wrapped(prefix: str, text: str) -> list[str]:
    lines = textwrap.wrap(
        text, width=WRAP, initial_indent=prefix, subsequent_indent=" " * len(prefix),
        break_long_words=True, break_on_hyphens=False,
    )
    return lines or [prefix.rstrip()]


def box_lines(m: Module, detail: int) -> list[str]:
    """Body lines of a module's box at `detail` 1-3 (detail 0 draws the id only).

    * 1: `id  name`, then the APIs out and in.
    * 2: adds the head line `lang · model · state` after the title.
    * 3: adds owned paths (`•`) and acceptance commands (`$`).
    """
    if detail <= 0:
        return [m.id]
    lines = [f"{m.id}  {m.name}"]
    if detail >= 2:
        lines.append(f"{m.lang} · {m.model} · {m.state}")
    lines.append(f"out: {api_names(m.produces)}")
    lines.append(f"in:  {api_names(m.consumes)}")
    if detail >= 3:
        for p in m.paths:
            lines += _wrapped("• ", p)
        for c in m.acceptance:
            lines += _wrapped("$ ", c)
    return lines


def api_line(arch: ArchMap, api_id: str, detail: int) -> str:
    """`C1 Schema quiver ─ coordinator → A, B`; detail 3 appends `[files]`."""
    a = arch.api(api_id)
    base = f"{a.id} {a.name} ─ {a.producer} → {', '.join(a.consumers)}"
    return base + f"   [{', '.join(a.files)}]" if detail >= 3 else base
