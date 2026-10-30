import BioMech.Gen.Model

/-!
# Pipeline emitters: `generated/pipeline.ninja`, `generated/py/pipeline_paths.py`

`pipeline.ninja` holds one `rule` per stage, running `$python -m <module>` with
the module named by `Stage.script`, and one `build` statement per stage, in
`topoOrder`: targets from `Stage.outputs`, explicit dependencies from
`Stage.inputs`, and implicit dependencies from `Stage.codeInputs` (the stage's
script and the scripts its code imports), so an edited script reruns every
stage that runs its code. A phony target named after each stage builds that
stage and its upstream stages, e.g. `ninja -f generated/pipeline.ninja
loadModel`. A directory artefact (a path with a trailing `/`)
appears without the slash, so ninja tracks the directory itself. Run it from the
repository root: `ninja -f generated/pipeline.ninja`.

`pipeline_paths.py` holds one constant per artefact (its path) and one `Stage`
record per stage (script, module, inputs, outputs, imported modules), so stage
scripts take their default paths from the Lean data.

## Terms

* *Implicit dependency*: a ninja input listed after `|`; a change to it reruns
  the statement, and the command line leaves it out of `$in`.
-/

namespace BioMech.Gen

/-- The interpreter the ninja rules run, before ninja's `$` escaping: the
default environment prefix of `pipeline/env/setup.sh` (`BM_ENV_PREFIX`), with
`$HOME` expanded by the shell that runs each command. -/
def pipelinePython : String := "$HOME/.local/share/bm-opensim/bin/python"

/-- Escapes a ninja path: `$`, space, and `:` take a `$` prefix. -/
def ninjaPath (p : String) : String :=
  let p := if p.endsWith "/" then String.ofList (p.toList.dropLast) else p
  String.join (p.toList.map fun c => if c == '$' || c == ' ' || c == ':' then "$" ++ c.toString else c.toString)

/-- Escapes a ninja variable value: `$` becomes `$$`. -/
def ninjaValue (v : String) : String := v.replace "$" "$$"

def ninjaFile (p : PipelineSpec) : String :=
  let stmt (s : StageSpec) : List String :=
    [""] ++ hashComment "" s.doc ++
    [s!"rule {s.name}",
     s!"  command = $python -m {pyModuleOf s.script}",
     s!"  description = {ninjaValue s.name}: {ninjaValue (docSummary (s.doc.getD s.name))}",
     s!"build {" ".intercalate (s.outputs.map ninjaPath)}: {s.name} {" ".intercalate (s.inputs.map ninjaPath)} | {" ".intercalate (s.codeInputs.map ninjaPath)}",
     s!"build {s.name}: phony {" ".intercalate (s.outputs.map ninjaPath)}"]
  let lines :=
    [s!"# {headerText p.loc.file}",
     "# Pipeline build file: one rule and one build statement per stage, in topological order.",
     "# Run from the repository root: ninja -f generated/pipeline.ninja",
     "",
     "ninja_required_version = 1.3",
     "",
     "# The pipeline interpreter: the default prefix of pipeline/env/setup.sh.",
     s!"python = {ninjaValue pipelinePython}"] ++
    p.ordered.flatMap stmt
  "\n".intercalate lines ++ "\n"

/-! ## `pipeline_paths.py` -/

def pyStrTuple (xs : List String) : String :=
  match xs with
  | [x] => s!"({x},)"
  | _ => "(" ++ ", ".intercalate xs ++ ")"

/-- Checks that the generated constant names are distinct. -/
def checkDistinct (what : String) (names : List String) : Except String Unit :=
  match names.find? (fun n => names.count n > 1) with
  | some n => .error s!"{what}: two declarations spell the constant {n}"
  | none => .ok ()

def pipelinePaths (p : PipelineSpec) : Except String String := do
  let artConst (n : String) := upperSnake n
  let stageConst (n : String) := upperSnake n
  checkDistinct "pipeline_paths.py" (p.artefacts.map (artConst ·.name) ++ p.stages.map (stageConst ·.name) ++
    ["ARTEFACTS", "SOURCES", "STAGES", "TOPO_ORDER", "EDGES", "Stage"])
  let artLines (a : ArtefactSpec) :=
    [s!"{artConst a.name}: Final = {jsonQuote a.path}"] ++ pyDocstring "" a.doc ++ [""]
  let stageLines (s : StageSpec) :=
    [s!"{stageConst s.name}: Final = Stage(",
     s!"    name={jsonQuote s.name},",
     s!"    script={jsonQuote s.script},",
     s!"    module={jsonQuote (pyModuleOf s.script)},",
     s!"    inputs={pyStrTuple (s.reads.map artConst)},",
     s!"    outputs={pyStrTuple (s.writes.map artConst)},",
     s!"    imports={pyStrTuple (s.imports.filterMap fun n => (p.stage? n).map (jsonQuote <| pyModuleOf ·.script))},",
     ")"] ++ pyDocstring "" s.doc ++ [""]
  let lines :=
    [s!"# {headerText p.loc.file}",
     "\"\"\"Pipeline file paths, and the inputs and outputs of each stage.",
     "",
     "Paths are relative to the repository root; a trailing `/` marks a directory.",
     "Stage scripts take their default paths from here.",
     "\"\"\"",
     "", "from __future__ import annotations", "",
     "from typing import Final, NamedTuple", "", ""] ++
    ["class Stage(NamedTuple):",
     "    \"\"\"A pipeline stage: its script and the files it reads and writes.\"\"\"",
     "", "    name: str", "    \"\"\"The stage's name in Lean, e.g. `loadModel`.\"\"\"",
     "    script: str", "    \"\"\"The stage's script, relative to the repository root.\"\"\"",
     "    module: str", "    \"\"\"The module `python -m` runs, e.g. `pipeline.load_model`.\"\"\"",
     "    inputs: tuple[str, ...]", "    \"\"\"Paths the stage reads (`Stage.inputs`).\"\"\"",
     "    outputs: tuple[str, ...]", "    \"\"\"Paths the stage writes (`Stage.outputs`).\"\"\"",
     "    imports: tuple[str, ...]",
     "    \"\"\"Modules of other stages the stage's script imports (`Stage.imports`), e.g. `pipeline.load_model`.\"\"\"",
     "", ""] ++
    p.artefacts.flatMap artLines ++ [""] ++
    p.stages.flatMap stageLines ++ [""] ++
    ["ARTEFACTS: Final[dict[str, str]] = {"] ++
    p.artefacts.map (fun a => s!"    {jsonQuote a.name}: {artConst a.name},") ++ ["}",
     "\"\"\"Every artefact by its Lean name.\"\"\"", "",
     s!"SOURCES: Final[tuple[str, ...]] = {pyStrTuple ((p.artefacts.filter (·.isSource)).map (artConst ·.name))}",
     "\"\"\"Paths maintained outside the pipeline.\"\"\"", "",
     s!"STAGES: Final[tuple[Stage, ...]] = {pyStrTuple (p.stages.map (stageConst ·.name))}",
     "\"\"\"Every stage, in declaration order.\"\"\"", "",
     s!"TOPO_ORDER: Final[tuple[Stage, ...]] = {pyStrTuple (p.topoOrder.map stageConst)}",
     "\"\"\"The order the stages run in (`topoOrder`).\"\"\"", "",
     "EDGES: Final[tuple[tuple[Stage, Stage], ...]] = ("] ++
    p.edges.map (fun (a, b) => s!"    ({stageConst a}, {stageConst b}),") ++ [")"] ++
    pyDocstring "" p.edgesDoc
  return "\n".intercalate lines ++ "\n"

end BioMech.Gen
