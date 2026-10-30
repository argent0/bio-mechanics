
/-!
# Module map (contract C4)

Every module of the project (one per workstream, plus the coordinator), the
paths each module owns, and every API between modules: which module generates
it and which modules consume it.

`lake exe arch` reads this file:
* `check` — every tracked file has exactly one owner (see `BioMech.Arch.owner`).
* `export` — writes `generated/modules.json`.
* `print --detail N` — draws the map as text, generators above consumers.

Path patterns: a pattern ending in `/` owns everything below that directory; a
pattern holding `*` matches any characters within one path segment; any other
pattern names one file. The most specific (longest) matching pattern wins.
-/

namespace BioMech.Arch

/-- Module identifiers: one per workstream in `plan.md`, plus the coordinator. -/
inductive ModuleId
  | coordinator | A | B | C | D | E | E2 | E3 | F | G | H | P1 | P2
  deriving DecidableEq, Repr, Inhabited

/-- API identifiers: the contracts between modules. -/
inductive ApiId
  | C1 | C2 | C3 | C4 | C5 | C6
  deriving DecidableEq, Repr, Inhabited

/-- Where a module stands. `planned` modules appear on the map before their code exists. -/
inductive ModState
  | planned | running | review | merged
  deriving DecidableEq, Repr, Inhabited

structure Module where
  id : ModuleId
  name : String
  /-- Main implementation language. -/
  lang : String
  /-- Model tier of the agent that owns the module (`plan.md`, Model selection). -/
  model : String
  state : ModState
  /-- Owned path patterns, relative to the repository root. -/
  paths : List String
  /-- Exact commands that accept the module's work. -/
  acceptance : List String

structure Api where
  id : ApiId
  name : String
  /-- Files that hold the API, relative to the repository root. -/
  files : List String
  producer : ModuleId
  consumers : List ModuleId

def modules : List Module := [
  { id := .coordinator, name := "Coordinator", lang := "Lean", model := "opus", state := .running,
    paths := ["CLAUDE.md", "handover.md", "plan.md", "prompt.md", "TASKS.md", "DECISIONS.md",
      ".gitignore", "pyproject.toml", "scripts/", "tests/", "generated/", "data/fixtures/",
      "pipeline/__init__.py", "spec/lakefile.lean", "spec/lean-toolchain", "spec/lake-manifest.json",
      "spec/BioMech/Schema.lean", "spec/BioMech/Architecture.lean", "spec/BioMech/Arch/",
      "spec/BioMech/ArchMain.lean"],
    acceptance := ["scripts/gate.sh"] },
  { id := .A, name := "Lean FSMs", lang := "Lean", model := "opus", state := .merged,
    paths := ["spec/BioMech/GaitFsm.lean", "spec/BioMech/UiFsm.lean"],
    acceptance := ["cd spec && lake build", "! grep -n sorry spec/BioMech/GaitFsm.lean spec/BioMech/UiFsm.lean"] },
  { id := .B, name := "Lean graphs", lang := "Lean", model := "opus", state := .running,
    paths := ["spec/BioMech/Pipeline.lean", "spec/BioMech/Components.lean", "spec/BioMech/Acyclic.lean"],
    acceptance := ["cd spec && lake build", "! grep -n sorry spec/BioMech/Pipeline.lean spec/BioMech/Components.lean spec/BioMech/Acyclic.lean"] },
  { id := .C, name := "Emitters", lang := "Lean", model := "opus", state := .planned,
    paths := ["spec/BioMech/Gen/"],
    acceptance := ["cd spec && lake exe gen && git diff --exit-code -- ../generated", "ninja -n -f generated/pipeline.ninja"] },
  { id := .D, name := "Data acquisition", lang := "Python", model := "sonnet", state := .running,
    paths := ["data/raw/", "pipeline/env/"],
    acceptance := ["python -c \"import opensim\""] },
  { id := .E, name := "Web scaffold", lang := "TypeScript", model := "sonnet", state := .merged,
    paths := ["web/"],
    acceptance := ["cd web && npx tsc --noEmit", "cd web && npm test", "cd web && npm run build"] },
  { id := .E2, name := "ArchitectureView", lang := "TypeScript", model := "sonnet", state := .planned,
    paths := ["web/src/architecture/"],
    acceptance := ["cd web && npx tsc --noEmit"] },
  { id := .E3, name := "Movement views", lang := "TypeScript", model := "sonnet", state := .planned,
    paths := ["web/src/viewer/", "web/src/timeline/", "web/src/phase/"],
    acceptance := ["cd web && npx tsc --noEmit", "cd web && npx eslint src"] },
  { id := .F, name := "Lean checkers", lang := "Lean", model := "opus", state := .planned,
    paths := ["spec/BioMech/CheckGraph.lean", "spec/BioMech/Conform.lean"],
    acceptance := ["cd spec && lake exe checkGraph ../data/fixtures/graph.sample.json"] },
  { id := .G, name := "CI and traces", lang := "YAML", model := "sonnet", state := .planned,
    paths := [".github/workflows/", "web/src/trace/"],
    acceptance := ["CI green on main"] },
  { id := .H, name := "Arch viewer", lang := "Python", model := "sonnet", state := .merged,
    paths := ["tools/"],
    acceptance := ["mypy tools", "pytest tools", "python -m tools.arch print --detail 3", "python -m tools.arch svg -o arch.svg"] },
  { id := .P1, name := "Pipeline stages 1-3", lang := "Python", model := "opus", state := .planned,
    paths := ["pipeline/load_model.py", "pipeline/static_opt.py", "pipeline/moment_arms.py",
      "pipeline/tests/test_p1_*.py"],
    acceptance := ["mypy pipeline", "pytest pipeline/tests -k p1"] },
  { id := .P2, name := "Pipeline stages 4-7", lang := "Python", model := "opus", state := .planned,
    paths := ["pipeline/segment_phases.py", "pipeline/label_roles.py", "pipeline/enrich_anatomy.py",
      "pipeline/export_*.py", "pipeline/config/", "pipeline/tests/test_p2_*.py",
      "data/curated/", "data/out/"],
    acceptance := ["ninja -f generated/pipeline.ninja", "cd spec && lake exe checkGraph ../data/out/graph.json"] }
]

def apis : List Api := [
  { id := .C1, name := "Schema quiver", files := ["spec/BioMech/Schema.lean"],
    producer := .coordinator, consumers := [.A, .B, .C, .F] },
  { id := .C2, name := "Generated types", files := ["generated/ts/types.ts", "generated/py/schema.py"],
    producer := .C, consumers := [.E, .P1, .P2, .E3] },
  { id := .C3, name := "graph.json", files := ["data/fixtures/graph.sample.json", "data/out/graph.json"],
    producer := .P2, consumers := [.E, .F, .E3] },
  { id := .C4, name := "Module map", files := ["spec/BioMech/Architecture.lean", "generated/modules.json"],
    producer := .coordinator, consumers := [.H] },
  { id := .C5, name := "FSMs", files := ["spec/BioMech/GaitFsm.lean", "spec/BioMech/UiFsm.lean"],
    producer := .A, consumers := [.C, .F] },
  { id := .C6, name := "Pipeline and component graphs",
    files := ["spec/BioMech/Pipeline.lean", "spec/BioMech/Components.lean"],
    producer := .B, consumers := [.C] }
]

def ModuleId.all : List ModuleId :=
  [.coordinator, .A, .B, .C, .D, .E, .E2, .E3, .F, .G, .H, .P1, .P2]

/-- Producer → consumer edges between modules, one per API and consumer. -/
def edges : List (ModuleId × ModuleId) :=
  apis.flatMap fun a => a.consumers.map fun c => (a.producer, c)

/-- One round of longest-path layering: a module sits one layer below every
module that produces an API it consumes. -/
def layerStep (l : ModuleId → Nat) (m : ModuleId) : Nat :=
  (edges.filter (·.2 == m)).foldl (fun acc e => max acc (l e.1 + 1)) 0

/-- Layer of each module (0 = top). The map is drawn with generators above
consumers. -/
def layer : ModuleId → Nat :=
  (List.range ModuleId.all.length).foldl (fun l _ => layerStep l) (fun _ => 0)

/-- Generators sit strictly above their consumers, so the API graph is acyclic. -/
theorem layered : ∀ e ∈ edges, layer e.1 < layer e.2 := by decide

/-- `ModuleId.all` lists every module. -/
theorem ModuleId.mem_all (m : ModuleId) : m ∈ ModuleId.all := by cases m <;> decide

/-- Each module appears exactly once in `modules`. -/
theorem modules_ids : modules.map (·.id) = ModuleId.all := by decide

/-- Each API appears exactly once in `apis`. -/
theorem apis_ids : apis.map (·.id) = [.C1, .C2, .C3, .C4, .C5, .C6] := by decide

def lookup (m : ModuleId) : Option Module := modules.find? (·.id == m)

end BioMech.Arch
