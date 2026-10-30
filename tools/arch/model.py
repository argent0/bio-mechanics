"""Typed, validated model of `generated/modules.json` (contract C4)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

#: Location of the exported map, relative to the repository root.
DEFAULT_MAP = Path("generated/modules.json")


class MapError(ValueError):
    """The map file is unreadable or does not follow the contract."""


@dataclass(frozen=True)
class Module:
    """One module of the map (one workstream)."""

    id: str
    name: str
    lang: str
    model: str
    state: str
    layer: int
    paths: tuple[str, ...]
    acceptance: tuple[str, ...]
    produces: tuple[str, ...]
    consumes: tuple[str, ...]


@dataclass(frozen=True)
class Api:
    """A contract between modules: one producer, several consumers."""

    id: str
    name: str
    files: tuple[str, ...]
    producer: str
    consumers: tuple[str, ...]


@dataclass(frozen=True)
class ArchMap:
    """The whole map. `modules` and `apis` keep the order of the file."""

    generated: str
    modules: tuple[Module, ...]
    apis: tuple[Api, ...]

    def module(self, module_id: str) -> Module:
        for m in self.modules:
            if m.id == module_id:
                return m
        raise KeyError(module_id)

    def api(self, api_id: str) -> Api:
        for a in self.apis:
            if a.id == api_id:
                return a
        raise KeyError(api_id)


def _obj(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise MapError(f"{where}: expected an object")
    return value


def _str(d: Mapping[str, object], key: str, where: str) -> str:
    v = d.get(key)
    if not isinstance(v, str):
        raise MapError(f"{where}: field '{key}' must be a string")
    return v


def _int(d: Mapping[str, object], key: str, where: str) -> int:
    v = d.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise MapError(f"{where}: field '{key}' must be a non-negative integer")
    return v


def _strs(d: Mapping[str, object], key: str, where: str) -> tuple[str, ...]:
    v = d.get(key)
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise MapError(f"{where}: field '{key}' must be a list of strings")
    return tuple(str(x) for x in v)


def _list(d: Mapping[str, object], key: str) -> list[object]:
    v = d.get(key)
    if not isinstance(v, list):
        raise MapError(f"top level: field '{key}' must be a list")
    return v


def _unique(items: list[str], what: str) -> None:
    seen: set[str] = set()
    for i in items:
        if i in seen:
            raise MapError(f"duplicate {what} id '{i}'")
        seen.add(i)


def parse_map(data: object) -> ArchMap:
    """Build an `ArchMap` from decoded JSON, checking every contract rule.

    Rules: field types; unique ids; producers and consumers name existing modules;
    each module's `produces`/`consumes` agree with the APIs; a producer sits in a
    strictly smaller layer than each consumer (generators above consumers).
    """
    top = _obj(data, "top level")
    generated = top.get("$generated", "")
    modules = tuple(
        Module(
            id=_str(o, "id", f"module #{i}"),
            name=_str(o, "name", f"module #{i}"),
            lang=_str(o, "lang", f"module #{i}"),
            model=_str(o, "model", f"module #{i}"),
            state=_str(o, "state", f"module #{i}"),
            layer=_int(o, "layer", f"module #{i}"),
            paths=_strs(o, "paths", f"module #{i}"),
            acceptance=_strs(o, "acceptance", f"module #{i}"),
            produces=_strs(o, "produces", f"module #{i}"),
            consumes=_strs(o, "consumes", f"module #{i}"),
        )
        for i, o in ((i, _obj(x, f"module #{i}")) for i, x in enumerate(_list(top, "modules")))
    )
    apis = tuple(
        Api(
            id=_str(o, "id", f"api #{i}"),
            name=_str(o, "name", f"api #{i}"),
            files=_strs(o, "files", f"api #{i}"),
            producer=_str(o, "producer", f"api #{i}"),
            consumers=_strs(o, "consumers", f"api #{i}"),
        )
        for i, o in ((i, _obj(x, f"api #{i}")) for i, x in enumerate(_list(top, "apis")))
    )
    result = ArchMap(generated if isinstance(generated, str) else "", modules, apis)
    _check(result)
    return result


def _check(m: ArchMap) -> None:
    _unique([x.id for x in m.modules], "module")
    _unique([a.id for a in m.apis], "api")
    layer = {x.id: x.layer for x in m.modules}
    for a in m.apis:
        if a.producer not in layer:
            raise MapError(f"api {a.id}: unknown producer '{a.producer}'")
        for c in a.consumers:
            if c not in layer:
                raise MapError(f"api {a.id}: unknown consumer '{c}'")
            if layer[a.producer] >= layer[c]:
                raise MapError(f"api {a.id}: producer {a.producer} must sit above consumer {c}")
        if a.producer in a.consumers:
            raise MapError(f"api {a.id}: producer {a.producer} also consumes it")
    for x in m.modules:
        made = tuple(a.id for a in m.apis if a.producer == x.id)
        used = tuple(a.id for a in m.apis if x.id in a.consumers)
        if set(x.produces) != set(made):
            raise MapError(f"module {x.id}: 'produces' disagrees with the apis")
        if set(x.consumes) != set(used):
            raise MapError(f"module {x.id}: 'consumes' disagrees with the apis")


def load_map(path: Path | str) -> ArchMap:
    """Read and validate the map file at `path`."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise MapError(f"cannot read {path}: {e.strerror or e}") from e
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as e:
        raise MapError(f"{path}: invalid JSON ({e})") from e
    return parse_map(data)
