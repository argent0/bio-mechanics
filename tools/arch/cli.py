"""Command line of `python -m tools.arch`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.arch.model import DEFAULT_MAP, MapError, load_map
from tools.arch.text import render


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--map", dest="map_sub", type=Path, default=None,
                        help=f"module map (default {DEFAULT_MAP})")
    p = argparse.ArgumentParser(prog="python -m tools.arch", description="View the module map.")
    p.add_argument("--map", dest="map_top", type=Path, default=None,
                   help=f"module map (default {DEFAULT_MAP})")
    sub = p.add_subparsers(dest="command", required=True)
    pr = sub.add_parser("print", parents=[common], help="draw the map as text")
    pr.add_argument("--detail", type=int, choices=range(4), default=1)
    sv = sub.add_parser("svg", parents=[common], help="write a standalone SVG")
    sv.add_argument("-o", "--output", type=Path, required=True)
    sv.add_argument("--detail", type=int, choices=range(4), default=2)
    wa = sub.add_parser("watch", parents=[common], help="live terminal map")
    wa.add_argument("--detail", type=int, choices=range(4), default=1)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path: Path = args.map_sub or args.map_top or DEFAULT_MAP
    try:
        if args.command == "watch":
            from tools.arch.watch import watch

            return watch(path, args.detail)
        arch = load_map(path)
        if args.command == "print":
            sys.stdout.write("\n".join(render(arch, args.detail).lines) + "\n")
        else:
            from tools.arch.svg import render_svg

            args.output.write_text(render_svg(arch, args.detail), encoding="utf-8")
            print(f"wrote {args.output}")
    except MapError as e:
        print(f"arch: {e}", file=sys.stderr)
        return 2
    return 0
