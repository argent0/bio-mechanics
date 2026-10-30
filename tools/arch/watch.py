"""Terminal UI: the module map, live.

Keys: arrows or `hjkl` scroll, PgUp/PgDn page, `+`/`-` zoom (detail 0-3), Tab and
Shift-Tab (or `n`/`p`) cycle the selected box, whose APIs light up with the boxes at
their other ends, Esc clears the selection, `q` quits. The map file is polled every
`POLL_SECONDS`; a change reloads and redraws.

The logic splits so that tests run without a terminal: `WatchApp` holds the state and
turns keys and file changes into `Row`s (pure), and `run_loop` talks to any `Screen`.
"""

from __future__ import annotations

import curses
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from tools.arch.model import ArchMap, MapError, load_map
from tools.arch.text import EDGE, RELATED, SELECTED, Rendered, Span, render

#: Seconds between looks at the map file (the requirement is a reload within 1 s).
POLL_SECONDS = 0.25

# Key codes (curses values, so tests need no terminal).
KEY_TAB, KEY_ESC = 9, 27
KEY_DOWN, KEY_UP, KEY_LEFT, KEY_RIGHT = 258, 259, 260, 261
KEY_HOME, KEY_BACKTAB, KEY_NPAGE, KEY_PPAGE = 262, 353, 338, 339
KEY_RESIZE = 410


class Screen(Protocol):
    """The part of a curses window the loop uses."""

    def getmaxyx(self) -> tuple[int, int]: ...
    def erase(self) -> None: ...
    def put(self, y: int, x: int, text: str, attr: int) -> None: ...
    def refresh(self) -> None: ...
    def getch(self) -> int: ...
    def set_timeout(self, ms: int) -> None: ...


@dataclass
class Row:
    """One visible screen row: its text and the highlight spans inside it."""

    text: str
    spans: list[tuple[int, int, str]] = field(default_factory=list)


def visible(rendered: Rendered, top: int, left: int, height: int, width: int) -> list[Row]:
    """Clip `rendered` to a window of `height` x `width` cells at (`top`, `left`)."""
    by_line: dict[int, list[Span]] = {}
    for s in rendered.spans:
        by_line.setdefault(s.line, []).append(s)
    rows: list[Row] = []
    for y in range(top, min(top + height, len(rendered.lines))):
        text = rendered.lines[y][left : left + width]
        spans = [(max(s.start, left) - left, min(s.end, left + width) - left, s.style)
                 for s in by_line.get(y, []) if s.end > left and s.start < left + width]
        rows.append(Row(text, spans))
    return rows


class WatchApp:
    """State of the watch UI: map, detail, scroll offset and selection."""

    def __init__(self, path: Path, detail: int = 1) -> None:
        self.path = path
        self.detail = max(0, min(3, detail))
        self.top = 0
        self.left = 0
        self.selected: str | None = None
        self.error = ""
        self.loaded_at = ""
        self.dirty = True
        self.arch: ArchMap | None = None
        self._stamp: tuple[int, int, int] | None = None
        self._rendered: Rendered | None = None
        self._reload()

    def _stat(self) -> tuple[int, int, int] | None:
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    def _reload(self) -> None:
        self._stamp = self._stat()
        try:
            self.arch = load_map(self.path)
            self.error = ""
            self.loaded_at = time.strftime("%H:%M:%S")
            if self.selected and all(m.id != self.selected for m in self.arch.modules):
                self.selected = None
        except MapError as e:
            self.error = str(e)
        self._rendered = None
        self.dirty = True

    def poll(self) -> bool:
        """Reload when the file changed; return True when the display needs a redraw."""
        if self._stat() != self._stamp:
            self._reload()
        return self.dirty

    def rendered(self) -> Rendered | None:
        if self.arch is None:
            return None
        if self._rendered is None:
            self._rendered = render(self.arch, self.detail, self.selected)
        return self._rendered

    def order(self) -> list[str]:
        """Module ids in drawing order (top row first, left to right)."""
        r = self.rendered()
        return [] if r is None else [m for m, _ in sorted(r.boxes.items(), key=lambda kv: (kv[1].y, kv[1].x))]

    def _select(self, step: int, height: int, width: int) -> None:
        ids = self.order()
        if not ids:
            return
        i = ids.index(self.selected) + step if self.selected in ids else (0 if step > 0 else -1)
        self.selected = ids[i % len(ids)]
        self._rendered = None
        self._reveal(height, width)

    def _reveal(self, height: int, width: int) -> None:
        r = self.rendered()
        if r is None or self.selected is None or self.selected not in r.boxes:
            return
        b = r.boxes[self.selected]
        if b.y < self.top or b.y + b.h > self.top + height - 1:
            self.top = max(0, b.y - 1)
        if b.x < self.left or b.x + b.w > self.left + width:
            self.left = max(0, b.x - 2)

    def handle_key(self, key: int, height: int = 24, width: int = 80) -> bool:
        """Apply `key`; return False to quit."""
        page = max(1, height - 3)
        if key in (ord("q"), ord("Q")):
            return False
        if key in (ord("+"), ord("=")) and self.detail < 3:
            self.detail += 1
        elif key in (ord("-"), ord("_")) and self.detail > 0:
            self.detail -= 1
        elif key in (KEY_TAB, ord("n")):
            self._select(1, height, width)
        elif key in (KEY_BACKTAB, ord("p")):
            self._select(-1, height, width)
        elif key == KEY_ESC:
            self.selected = None
        elif key in (KEY_DOWN, ord("j")):
            self.top += 1
        elif key in (KEY_UP, ord("k")):
            self.top -= 1
        elif key in (KEY_RIGHT, ord("l")):
            self.left += 4
        elif key in (KEY_LEFT, ord("h")):
            self.left -= 4
        elif key == KEY_NPAGE:
            self.top += page
        elif key == KEY_PPAGE:
            self.top -= page
        elif key in (KEY_HOME, ord("g")):
            self.top = self.left = 0
        elif key == ord("G"):
            self.top = 10**6
        self._rendered = None
        self._clamp(height, width)
        self.dirty = True
        return True

    def _clamp(self, height: int, width: int) -> None:
        r = self.rendered()
        if r is None:
            self.top = self.left = 0
            return
        longest = max((len(s) for s in r.lines), default=0)
        self.top = max(0, min(self.top, len(r.lines) - max(1, height - 1)))
        self.left = max(0, min(self.left, longest - width))

    def status(self, width: int) -> str:
        sel = self.selected or "-"
        err = f" | ERROR {self.error}" if self.error else ""
        text = (f" detail {self.detail} | selected {sel} | {self.path} @ {self.loaded_at}{err}"
                f" | Tab select  +/- zoom  arrows scroll  q quit")
        return text[:width].ljust(width)

    def frame(self, height: int, width: int) -> list[Row]:
        """Rows for a screen of `height` x `width`: the map window, then the status line."""
        self._clamp(height, width)
        r = self.rendered()
        rows = [] if r is None else visible(r, self.top, self.left, height - 1, width)
        rows += [Row("")] * (height - 1 - len(rows))
        rows.append(Row(self.status(width), [(0, width, "status")]))
        self.dirty = False
        return rows


def draw(screen: Screen, app: WatchApp, attrs: dict[str, int]) -> None:
    """Paint one frame of `app` on `screen`."""
    height, width = screen.getmaxyx()
    screen.erase()
    for y, row in enumerate(app.frame(height, width)):
        if y >= height - 1:
            screen.put(y, 0, row.text[: max(0, width - 1)], attrs.get("status", 0))
            continue
        screen.put(y, 0, row.text, 0)
        for a, b, style in row.spans:
            screen.put(y, a, row.text[a:b], attrs.get(style, 0))
    screen.refresh()


def run_loop(screen: Screen, app: WatchApp, attrs: dict[str, int], poll: float = POLL_SECONDS) -> None:
    """Redraw on every change of the map file or keypress until `q`."""
    screen.set_timeout(int(poll * 1000))
    last_size = screen.getmaxyx()
    while True:
        app.poll()
        if screen.getmaxyx() != last_size:
            last_size, app.dirty = screen.getmaxyx(), True
        if app.dirty:
            draw(screen, app, attrs)
        key = screen.getch()
        if key != -1:
            h, w = screen.getmaxyx()
            if not app.handle_key(key, h, w):
                return


class _CursesScreen:
    """Adapter from `curses.window` to `Screen`."""

    def __init__(self, win: curses.window) -> None:
        self.win = win
        win.keypad(True)

    def getmaxyx(self) -> tuple[int, int]:
        return self.win.getmaxyx()

    def erase(self) -> None:
        self.win.erase()

    def put(self, y: int, x: int, text: str, attr: int) -> None:
        try:
            self.win.addnstr(y, x, text, max(0, self.getmaxyx()[1] - x), attr)
        except curses.error:
            pass  # writing the bottom-right cell raises; the text is on screen

    def refresh(self) -> None:
        self.win.refresh()

    def getch(self) -> int:
        return int(self.win.getch())

    def set_timeout(self, ms: int) -> None:
        self.win.timeout(ms)


def _curses_attrs() -> dict[str, int]:
    attrs = {SELECTED: curses.A_REVERSE | curses.A_BOLD, RELATED: curses.A_BOLD | curses.A_UNDERLINE,
             EDGE: curses.A_BOLD, "status": curses.A_REVERSE}
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        attrs[SELECTED] = curses.color_pair(1) | curses.A_BOLD
        attrs[RELATED] = curses.color_pair(2) | curses.A_BOLD
        attrs[EDGE] = curses.color_pair(3) | curses.A_BOLD
    return attrs


def _main(win: curses.window, path: Path, detail: int) -> None:
    curses.curs_set(0)
    run_loop(_CursesScreen(win), WatchApp(path, detail), _curses_attrs())


def watch(path: Path, detail: int) -> int:
    """Run the interactive viewer; returns the process exit code."""
    app = WatchApp(path, detail)
    if app.arch is None:
        raise MapError(app.error)
    curses.wrapper(_main, path, detail)
    return 0
