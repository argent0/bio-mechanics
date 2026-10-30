"""The watch UI without a terminal: keys, selection, and live reload."""

import json
import threading
import time
from pathlib import Path

from tools.arch.model import load_map
from tools.arch.watch import (
    KEY_TAB, Screen, WatchApp, draw, run_loop,
)

REAL_MAP = Path(__file__).resolve().parents[2] / "generated" / "modules.json"
ATTRS = {"selected": 1, "related": 2, "edge": 4, "status": 8}


class FakeScreen:
    """A screen that records the text and attributes of the latest frame."""

    def __init__(self, h: int = 60, w: int = 200) -> None:
        self.h, self.w = h, w
        self.cells: dict[tuple[int, int], tuple[str, int]] = {}
        self.frames = 0
        self.stop = threading.Event()
        self.keys: list[int] = []
        self.lock = threading.Lock()

    def getmaxyx(self) -> tuple[int, int]:
        return self.h, self.w

    def erase(self) -> None:
        with self.lock:
            self.cells = {}

    def put(self, y: int, x: int, text: str, attr: int) -> None:
        with self.lock:
            for i, ch in enumerate(text):
                self.cells[(y, x + i)] = (ch, attr)

    def refresh(self) -> None:
        with self.lock:
            self.frames += 1

    def getch(self) -> int:
        if self.keys:
            return self.keys.pop(0)
        if self.stop.is_set():
            return ord("q")
        time.sleep(0.02)
        return -1

    def set_timeout(self, ms: int) -> None:
        pass

    def text(self) -> str:
        with self.lock:
            return "\n".join(
                "".join(self.cells.get((y, x), (" ", 0))[0] for x in range(self.w)).rstrip()
                for y in range(self.h))


def test_fake_screen_is_a_screen() -> None:
    s: Screen = FakeScreen()
    assert s.getmaxyx() == (60, 200)


def test_redraw_after_map_edit(tmp_path: Path) -> None:
    path = tmp_path / "modules.json"
    path.write_text(REAL_MAP.read_text(encoding="utf-8"), encoding="utf-8")
    arch = load_map(path)
    h = arch.module("H")
    old = f"{h.lang} · {h.model} · {h.state}"
    new_state = "review" if h.state != "review" else "planned"
    new = f"{h.lang} · {h.model} · {new_state}"
    screen = FakeScreen()
    app = WatchApp(path, detail=2)
    thread = threading.Thread(target=run_loop, args=(screen, app, ATTRS), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while old not in screen.text() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert old in screen.text()
        before = screen.text()
        data = json.loads(path.read_text(encoding="utf-8"))
        for m in data["modules"]:
            if m["id"] == "H":
                m["state"] = new_state
        edited = json.dumps(data, indent=2)
        time.sleep(0.05)
        t0 = time.monotonic()
        path.write_text(edited, encoding="utf-8")
        while new not in screen.text() and time.monotonic() - t0 < 2:
            time.sleep(0.02)
        elapsed = time.monotonic() - t0
        assert new in screen.text(), "no redraw within 2 s"
        assert elapsed < 1.5
        assert screen.text() != before
        path.write_text("{broken", encoding="utf-8")
        t0 = time.monotonic()
        while "ERROR" not in screen.text() and time.monotonic() - t0 < 2:
            time.sleep(0.02)
        assert "ERROR" in screen.text() and new in screen.text()
    finally:
        screen.stop.set()
        thread.join(timeout=2)
    assert not thread.is_alive()


def test_keys_zoom_select_scroll() -> None:
    app = WatchApp(REAL_MAP, detail=1)
    assert app.detail == 1
    app.handle_key(ord("+"))
    app.handle_key(ord("+"))
    app.handle_key(ord("+"))
    assert app.detail == 3
    for _ in range(5):
        app.handle_key(ord("-"))
    assert app.detail == 0
    app.handle_key(KEY_TAB)
    first = app.selected
    assert first == app.order()[0]
    app.handle_key(KEY_TAB)
    assert app.selected == app.order()[1]
    app.handle_key(ord("j"), 10, 80)
    assert app.top == 1
    app.handle_key(ord("k"), 10, 80)
    app.handle_key(ord("k"), 10, 80)
    assert app.top == 0
    assert app.handle_key(ord("q")) is False


def test_selection_is_drawn_with_attributes() -> None:
    screen = FakeScreen()
    app = WatchApp(REAL_MAP, detail=1)
    sel = next(m.id for m in load_map(REAL_MAP).modules if m.produces and m.consumes)
    app.selected = sel
    draw(screen, app, ATTRS)
    attrs = {a for _, a in screen.cells.values()}
    assert {1, 2, 4, 8} <= attrs
    assert "detail 1" in screen.text().splitlines()[-1] and f"selected {sel}" in screen.text()
