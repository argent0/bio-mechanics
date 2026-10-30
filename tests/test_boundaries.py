"""Import boundaries of the web app, checked against `generated/eslint-boundaries.json`.

The rules come from the component digraph in `spec/BioMech/Components.lean`
(emitted by `lake exe gen`). This test applies them to every `.ts` file under
`web/src/` (test files excepted, as the rules' `boundaries/ignore` says):

* a file under `web/src/` belongs to the element whose pattern it matches;
* each relative or `@gen/` import resolves to a file; when that file matches an
  element, the importer's element must allow it;
* imports of files outside every element pattern and outside `web/src/` (JSON
  data such as `generated/architecture.json` or the graph fixture) are data
  imports and pass; bare package names (`three`, `cytoscape`) pass.

ESLint's `eslint-plugin-boundaries` reads the same JSON; this test stands in for
it while `typescript-eslint` lacks support for the TypeScript major the app uses.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_SRC = ROOT / "web" / "src"
GEN_ALIAS = ("@gen/", "generated/ts/")

IMPORT = re.compile(
    r"""(?:^|;|\n)\s*(?:import|export)\b[^;'"]*?\bfrom\s*["']([^"']+)["']"""
    r"""|\bimport\s*["']([^"']+)["']"""
    r"""|\bimport\(\s*["']([^"']+)["']\s*\)""",
    re.S,
)


def load_rules() -> tuple[list[tuple[str, str]], dict[str, set[str]], list[str]]:
    spec = json.loads((ROOT / "generated" / "eslint-boundaries.json").read_text())
    settings = spec["settings"]
    elements = [(e["type"], e["pattern"]) for e in settings["boundaries/elements"]]
    allow = {
        source: set(rule["allow"])
        for rule in spec["rules"]["boundaries/element-types"][1]["rules"]
        for source in rule["from"]
    }
    return elements, allow, list(settings["boundaries/ignore"])


def element_of(rel: str, elements: list[tuple[str, str]]) -> str | None:
    for kind, pattern in elements:
        if fnmatch.fnmatchcase(rel, pattern):
            return kind
    return None


def resolve(importer: Path, spec: str) -> Path | None:
    """The file an import names, or None for a package import."""
    if spec.startswith(GEN_ALIAS[0]):
        base = ROOT / GEN_ALIAS[1] / spec[len(GEN_ALIAS[0]):]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    for candidate in (base, base.with_name(base.name + ".ts"), base / "index.ts"):
        if candidate.is_file():
            return candidate
    raise AssertionError(f"{importer.relative_to(ROOT)}: import {spec!r} resolves to no file")


def violations() -> list[str]:
    elements, allow, ignore = load_rules()
    errors: list[str] = []
    for path in sorted(WEB_SRC.rglob("*.ts")):
        rel = path.relative_to(ROOT).as_posix()
        if any(fnmatch.fnmatchcase(rel, pattern) for pattern in ignore):
            continue
        source = element_of(rel, elements)
        if source is None:
            errors.append(f"{rel}: belongs to no component")
            continue
        for match in IMPORT.finditer(path.read_text()):
            spec = next(group for group in match.groups() if group)
            target_path = resolve(path, spec)
            if target_path is None:
                continue
            target_rel = target_path.relative_to(ROOT).as_posix()
            target = element_of(target_rel, elements)
            if target is None:
                if target_rel.startswith("web/src/"):
                    errors.append(f"{rel}: imports {target_rel}, which belongs to no component")
                continue
            if target not in allow.get(source, set()):
                errors.append(f"{rel}: {source} imports {target} ({spec}), outside the component digraph")
    return errors


def test_web_imports_follow_component_digraph() -> None:
    assert violations() == []


def test_checker_catches_a_forbidden_import(tmp_path: Path) -> None:
    elements, allow, _ = load_rules()
    assert element_of("web/src/viewer/Viewer3D.ts", elements) == "Viewer3D"
    assert element_of("web/src/store/GraphStore.ts", elements) == "GraphStore"
    assert "GraphStore" not in allow["Viewer3D"]
