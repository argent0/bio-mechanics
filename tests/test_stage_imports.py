"""Each stage's script imports exactly the stage modules `Stage.imports` lists in
`spec/BioMech/Pipeline.lean`, and ninja reruns a stage when any script whose code
it runs changes.

* `Stage.imports` reaches Python as `pipeline_paths.Stage.imports` (module names,
  e.g. `pipeline.load_model`). The first test parses each stage script with `ast`
  and collects every import of a `pipeline` module, function bodies included.
* The second test reads `generated/pipeline.ninja`: each stage's implicit
  dependencies (after `|`) are its own script, then the scripts of the stages it
  reaches along the imports (`Stage.codeInputs`).
"""

from __future__ import annotations

import ast
from pathlib import Path

from pipeline_paths import STAGES, Stage

ROOT = Path(__file__).resolve().parent.parent
NINJA = ROOT / "generated" / "pipeline.ninja"
PACKAGE = "pipeline"


def pipeline_imports(script: Path) -> set[str]:
    """Every `pipeline.<module>` the script imports, at any depth of the file."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(script.read_text(), filename=str(script))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith(PACKAGE + "."))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = PACKAGE + ("." + node.module if node.module else "")
            else:
                base = node.module or ""
            if base == PACKAGE:
                found.update(f"{PACKAGE}.{a.name}" for a in node.names)
            elif base.startswith(PACKAGE + "."):
                found.add(base)
    return found


def test_lean_imports_match_scripts() -> None:
    for stage in STAGES:
        parsed = pipeline_imports(ROOT / stage.script)
        assert parsed == set(stage.imports), (
            f"{stage.script} imports {sorted(parsed)}; "
            f"Stage.imports of {stage.name} in spec/BioMech/Pipeline.lean lists {sorted(stage.imports)}"
        )


def code_scripts(stage: Stage, by_module: dict[str, Stage]) -> set[str]:
    """The scripts whose code the stage runs: its own and every script it reaches by imports."""
    seen = {stage.module}
    todo = list(stage.imports)
    while todo:
        module = todo.pop()
        if module not in seen:
            seen.add(module)
            todo.extend(by_module[module].imports)
    return {by_module[m].script for m in seen}


def implicit_deps() -> dict[str, list[str]]:
    """Rule name -> the implicit dependencies of its build statement in `pipeline.ninja`."""
    deps: dict[str, list[str]] = {}
    for line in NINJA.read_text().splitlines():
        if not line.startswith("build ") or " | " not in line:
            continue
        _, rhs = line.split(": ", 1)
        explicit, implicit = rhs.split(" | ", 1)
        deps[explicit.split()[0]] = implicit.split()
    return deps


def test_ninja_reruns_stages_on_imported_code() -> None:
    by_module = {s.module: s for s in STAGES}
    deps = implicit_deps()
    for stage in STAGES:
        listed = deps[stage.name]
        assert listed[0] == stage.script, f"{stage.name}: its own script comes first"
        assert set(listed) == code_scripts(stage, by_module), stage.name
