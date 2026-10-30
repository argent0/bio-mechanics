
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
  | S | L | D2 | W1 | G2 | M | P4 | W2
  deriving DecidableEq, Repr, Inhabited

/-- API identifiers: the contracts between modules. -/
inductive ApiId
  | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9
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
    paths := ["CLAUDE.md", "handover.md", "README.md", "plan.md", "prompt.md", "TASKS.md", "DECISIONS.md",
      ".gitignore", "pyproject.toml", "scripts/", "tests/", "generated/", "data/fixtures/",
      "pipeline/__init__.py", "spec/lakefile.lean", "spec/lean-toolchain", "spec/lake-manifest.json",
      "spec/BioMech/Schema.lean", "spec/BioMech/Architecture.lean", "spec/BioMech/Arch/",
      "spec/BioMech/ArchMain.lean"],
    acceptance := ["scripts/gate.sh"] },
  { id := .A, name := "Lean FSMs", lang := "Lean", model := "opus", state := .merged,
    paths := ["spec/BioMech/GaitFsm.lean", "spec/BioMech/UiFsm.lean"],
    acceptance := ["cd spec && lake build", "! grep -n sorry spec/BioMech/GaitFsm.lean spec/BioMech/UiFsm.lean"] },
  { id := .B, name := "Lean graphs", lang := "Lean", model := "opus", state := .merged,
    paths := ["spec/BioMech/Acyclic.lean"],
    acceptance := ["cd spec && lake build", "! grep -n sorry spec/BioMech/Pipeline.lean spec/BioMech/Components.lean spec/BioMech/Acyclic.lean"] },
  { id := .C, name := "Emitters", lang := "Lean", model := "opus", state := .merged,
    paths := [],
    acceptance := ["cd spec && lake exe gen && git diff --exit-code -- ../generated", "ninja -n -f generated/pipeline.ninja"] },
  { id := .D, name := "Data acquisition", lang := "Python", model := "sonnet", state := .merged,
    paths := ["data/raw/"],
    acceptance := ["~/.local/share/bm-opensim/bin/python pipeline/env/check_env.py"] },
  { id := .E, name := "Web scaffold", lang := "TypeScript", model := "sonnet", state := .merged,
    paths := ["web/"],
    acceptance := ["cd web && npx tsc --noEmit", "cd web && npm test", "cd web && npm run build"] },
  { id := .E2, name := "ArchitectureView", lang := "TypeScript", model := "sonnet", state := .merged,
    paths := ["web/src/architecture/"],
    acceptance := ["cd web && npx tsc --noEmit"] },
  { id := .E3, name := "Movement views", lang := "TypeScript", model := "sonnet", state := .merged,
    paths := ["web/src/timeline/"],
    acceptance := ["cd web && npx tsc --noEmit", "cd web && npm test", "pytest tests/test_boundaries.py"] },
  { id := .F, name := "Lean checkers", lang := "Lean", model := "opus", state := .merged,
    paths := ["spec/BioMech/CheckGraph.lean", "spec/BioMech/Conform.lean"],
    acceptance := ["cd spec && lake exe checkGraph ../data/fixtures/graph.sample.json",
      "cd spec && lake exe conform ../data/fixtures/trace.sample.json"] },
  { id := .G, name := "CI and traces", lang := "YAML", model := "sonnet", state := .merged,
    paths := ["web/src/trace/"],
    acceptance := ["CI green on main"] },
  { id := .H, name := "Arch viewer", lang := "Python", model := "sonnet", state := .merged,
    paths := ["tools/"],
    acceptance := ["mypy tools", "pytest tools", "python -m tools.arch print --detail 3", "python -m tools.arch svg -o arch.svg"] },
  { id := .P1, name := "Pipeline stages 1-3", lang := "Python", model := "opus", state := .merged,
    paths := ["pipeline/load_model.py", "pipeline/moment_arms.py",
      "pipeline/tests/test_p1_*.py"],
    acceptance := ["mypy pipeline", "~/.local/share/bm-opensim/bin/python -m pytest pipeline/tests -k p1"] },
  { id := .P2, name := "Pipeline stages 4-7", lang := "Python", model := "opus", state := .merged,
    paths := ["pipeline/segment_phases.py", "pipeline/config/", "pipeline/tests/test_p2_*.py",
      "data/curated/", "data/raw/ontology/"],
    acceptance := ["ninja -f generated/pipeline.ninja", "cd spec && lake exe checkGraph ../data/out/graph.json"] },
  -- The whole body (plan.md, Waves 1–2).
  { id := .S, name := "Lean spec additions", lang := "Lean", model := "opus", state := .planned,
    paths := ["spec/BioMech/Pipeline.lean", "spec/BioMech/Components.lean", "spec/BioMech/Gen/"],
    acceptance := ["cd spec && lake build", "! grep -n sorry spec/BioMech/Pipeline.lean spec/BioMech/Components.lean",
      "ninja -n -f generated/pipeline.ninja"] },
  { id := .L, name := "Left leg", lang := "Python", model := "opus", state := .planned,
    paths := ["pipeline/label_roles.py", "pipeline/enrich_anatomy.py", "pipeline/export_*.py",
      "pipeline/config/roles.yaml", "pipeline/tests/test_l_*.py", "data/out/"],
    acceptance := ["ninja -f generated/pipeline.ninja", "cd spec && lake exe checkGraph ../data/out/graph.json",
      "python scripts/compare_graph.py --within-committed <main graph.json> data/out/graph.json",
      "~/.local/share/bm-opensim/bin/python -m pytest pipeline/tests -k l_"] },
  { id := .D2, name := "Upper-body data", lang := "Python", model := "sonnet", state := .planned,
    paths := ["pipeline/env/", "data/raw/SHA256SUMS", "data/raw/SOURCES.md", "data/raw/holzbaur/",
      "data/raw/mortensen/", "data/raw/christophy/"],
    acceptance := ["~/.local/share/bm-opensim/bin/python pipeline/env/check_env.py"] },
  { id := .W1, name := "Web, whole-body views", lang := "TypeScript", model := "sonnet", state := .planned,
    paths := ["web/src/viewer/", "web/src/phase/", "web/src/graphview/", "web/src/region/"],
    acceptance := ["cd web && npx tsc --noEmit", "cd web && npm test", "pytest tests/test_boundaries.py"] },
  { id := .G2, name := "CI", lang := "YAML", model := "sonnet", state := .planned,
    paths := [".github/workflows/"],
    acceptance := ["CI green on main", "pipeline job under 15 minutes"] },
  { id := .M, name := "Model merge", lang := "Python", model := "opus", state := .planned,
    paths := ["pipeline/build_model.py", "pipeline/static_opt.py", "pipeline/config/model.yaml",
      "pipeline/tests/test_m_*.py"],
    acceptance := ["~/.local/share/bm-opensim/bin/python -m pytest pipeline/tests -k m_"] },
  { id := .P4, name := "Trunk and arm stages", lang := "Python", model := "opus", state := .planned,
    paths := ["pipeline/tests/test_p4_*.py"],
    acceptance := ["ninja -f generated/pipeline.ninja", "cd spec && lake exe checkGraph ../data/out/graph.json",
      "~/.local/share/bm-opensim/bin/python -m pytest pipeline/tests -k p4"] },
  { id := .W2, name := "Web, real output", lang := "TypeScript", model := "sonnet", state := .planned,
    paths := [],
    acceptance := ["cd web && npx tsc --noEmit", "cd web && npm test", "viewer at 30 fps or more, every muscle drawn"] }
]

def apis : List Api := [
  { id := .C1, name := "Schema quiver", files := ["spec/BioMech/Schema.lean"],
    producer := .coordinator, consumers := [.A, .B, .C, .F, .S] },
  { id := .C2, name := "Generated types", files := ["generated/ts/types.ts", "generated/py/schema.py"],
    producer := .S, consumers := [.E, .P1, .P2, .E3, .L, .W1, .M, .P4, .W2] },
  { id := .C3, name := "graph.json", files := ["data/fixtures/graph.sample.json", "data/out/graph.json"],
    producer := .L, consumers := [.E, .F, .E3, .W1, .W2] },
  { id := .C4, name := "Module map", files := ["spec/BioMech/Architecture.lean", "generated/modules.json"],
    producer := .coordinator, consumers := [.H] },
  { id := .C5, name := "FSMs", files := ["spec/BioMech/GaitFsm.lean", "spec/BioMech/UiFsm.lean"],
    producer := .A, consumers := [.C, .F] },
  { id := .C6, name := "Pipeline and component graphs",
    files := ["spec/BioMech/Pipeline.lean", "spec/BioMech/Components.lean"],
    producer := .S, consumers := [.C, .M] },
  { id := .C7, name := "trace.json", files := ["spec/BioMech/Conform.lean", "data/fixtures/trace.sample.json"],
    producer := .F, consumers := [.G] },
  { id := .C8, name := "Upper-body model data", files := ["pipeline/env/fetch_data.sh", "data/raw/SHA256SUMS"],
    producer := .D2, consumers := [.M, .G2] },
  { id := .C9, name := "Merged model", files := ["pipeline/config/model.yaml", "data/work/model.json"],
    producer := .M, consumers := [.P4] }
]

def ModuleId.all : List ModuleId :=
  [.coordinator, .A, .B, .C, .D, .E, .E2, .E3, .F, .G, .H, .P1, .P2, .S, .L, .D2, .W1, .G2, .M, .P4, .W2]

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
theorem apis_ids : apis.map (·.id) = [.C1, .C2, .C3, .C4, .C5, .C6, .C7, .C8, .C9] := by decide

def lookup (m : ModuleId) : Option Module := modules.find? (·.id == m)

end BioMech.Arch
