import BioMech.Gen.Eval
import BioMech.Gen.Text

/-!
# The specification as emitter data

Reads the two DFAs, the pipeline digraph, the component digraph, and every
theorem of `specModules` from the imported environment (`loadEnv`). Values come
from evaluating the Lean declarations (`evalTerm`); names, docstrings, and
source lines come from the environment. The emitters print these records and
nothing else, so the Lean declarations stay the single source of every
generated file.

## Terms

* *Explicit row*: a `(from, event, to)` row of a DFA's `transitions` list.
* *Complete table*: `step s e` for every state `s` and event `e`, evaluated in
  Lean; it holds the explicit rows and the implicit steps of absent pairs.
* *Implicit rule*: what the complete table does on pairs absent from the
  explicit rows, read off the table (`Implicit`).
-/

namespace BioMech.Gen
open Lean Meta

/-- A named value with its docstring. -/
structure Item where
  name : String
  doc : Option String

/-- Where a declaration sits in the source. -/
structure Loc where
  module : String
  /-- Source file relative to the repository root. -/
  file : String
  /-- Line of the declaration's name (1-based). -/
  line : Nat
  /-- First line of the declaration, its docstring included. -/
  startLine : Nat
  /-- Last line of the declaration. -/
  endLine : Nat

/-- The source location of `n`, from the declaration-range extension. -/
def locOf (n : Name) : MetaM Loc := do
  let env ← getEnv
  let some idx := env.getModuleIdxFor? n | throwError "{n} has no module"
  let some m := env.header.moduleNames[idx.toNat]? | throwError "{n} has no module"
  let some r ← findDeclarationRanges? n | throwError "{n} has no declaration range"
  return { module := m.toString, file := moduleFile m, line := r.selectionRange.pos.line,
           startLine := r.range.pos.line, endLine := r.range.endPos.line }

/-! ## DFAs -/

/-- Lean names an FSM emitter reads, relative to the FSM's namespace `ns`. -/
structure FsmConfig where
  /-- Identifier in `architecture.json` and diagram file names, e.g. `gaitFsm`. -/
  id : String
  ns : Name
  state : String
  event : String
  states : String
  events : String
  transitions : String
  step : String
  start : String
  accept : String
  /-- Further lists of states, e.g. `GaitPhase.phases`. -/
  stateLists : List String
  /-- Words over the events, e.g. `strideWord`. -/
  words : List String

/-- The gait DFA of `BioMech.GaitFsm`. -/
def gaitConfig : FsmConfig where
  id := "gaitFsm"
  ns := `BioMech.Gait
  state := "GaitPhase"
  event := "GaitEvent"
  states := "GaitPhase.all"
  events := "GaitEvent.all"
  transitions := "transitions"
  step := "step"
  start := "gaitDfa.start"
  accept := "acceptStates"
  stateLists := ["GaitPhase.phases", "GaitPhase.stance", "GaitPhase.swing"]
  words := ["strideWord"]

/-- The UI DFA of `BioMech.UiFsm`. -/
def uiConfig : FsmConfig where
  id := "uiFsm"
  ns := `BioMech.Ui
  state := "UiState"
  event := "UiEvent"
  states := "UiState.all"
  events := "UiEvent.all"
  transitions := "transitions"
  step := "step"
  start := "uiDfa.start"
  accept := "acceptStates"
  stateLists := []
  words := ["resetWord"]

/-- A list of values read from a Lean declaration, e.g. `strideWord`. -/
structure NamedList where
  /-- The declaration's name relative to the FSM namespace. -/
  lean : String
  doc : Option String
  values : List String

/-- The step on pairs absent from the explicit rows. -/
inductive Implicit
  /-- Every absent pair goes to this state. -/
  | sink (state : String)
  /-- Every absent pair leaves the state as it is. -/
  | selfLoop
  /-- Absent pairs go to various states; the complete table holds them. -/
  | mixed

structure FsmSpec where
  config : FsmConfig
  module : String
  stateDoc : Option String
  eventDoc : Option String
  /-- States in the order of `config.states`, with constructor docstrings. -/
  states : List Item
  events : List Item
  start : String
  accept : List String
  acceptDoc : Option String
  rows : List (String × String × String)
  rowsDoc : Option String
  stepDoc : Option String
  /-- Per state (in `states` order), the target of each event (in `events` order). -/
  table : List (String × List String)
  implicit : Implicit
  stateLists : List NamedList
  words : List NamedList
  loc : Loc

def fsmSpec (c : FsmConfig) : MetaM FsmSpec := do
  let q (n : String) : Name := c.ns ++ n.toName
  let st := q c.state
  let ev := q c.event
  let inNs (t : String) := s!"open {c.ns} in ({t})"
  let stateNames ← evalEnumList st (inNs c.states)
  let eventNames ← evalEnumList ev (inNs c.events)
  let sDocs ← ctorDocs st
  let eDocs ← ctorDocs ev
  let item (docs : List (String × Option String)) (n : String) : Item :=
    { name := n, doc := (docs.find? (·.1 == n)).bind (·.2) }
  let sNames ← ctorNames st
  let eNames ← ctorNames ev
  let rowIdx ← evalTerm (List (Nat × Nat × Nat))
    (inNs s!"{c.transitions}.map fun t => ({st}.ctorIdx t.1, {ev}.ctorIdx t.2.1, {st}.ctorIdx t.2.2)")
  let rows ← rowIdx.mapM fun (a, e, b) =>
    return (← ctorAt sNames st a, ← ctorAt eNames ev e, ← ctorAt sNames st b)
  let tableIdx ← evalTerm (List (List Nat))
    (inNs s!"({c.states}).map fun s => ({c.events}).map fun e => {st}.ctorIdx ({c.step} s e)")
  let targets ← tableIdx.mapM (·.mapM (ctorAt sNames st))
  let table := stateNames.zip targets
  let absent := table.flatMap fun (s, ts) => (eventNames.zip ts).filterMap fun (e, t) =>
    if rows.any (fun r => r.1 == s && r.2.1 == e) then none else some (s, t)
  let implicit :=
    if absent.all (fun p => p.1 == p.2) then .selfLoop
    else match absent with
      | (_, t) :: rest => if rest.all (·.2 == t) then .sink t else .mixed
      | [] => .selfLoop
  let namedList (ty : Name) (n : String) : MetaM NamedList := do
    return { lean := n, doc := ← docOf (q n), values := ← evalEnumList ty (inNs n) }
  let loc ← locOf st
  return {
    config := c, module := loc.module, stateDoc := ← docOf st, eventDoc := ← docOf ev,
    states := stateNames.map (item sDocs), events := eventNames.map (item eDocs),
    start := ← evalEnum st (inNs c.start),
    accept := ← evalEnumList st (inNs c.accept), acceptDoc := ← docOf (q c.accept),
    rows, rowsDoc := ← docOf (q c.transitions), stepDoc := ← docOf (q c.step),
    table, implicit,
    stateLists := ← c.stateLists.mapM (namedList st),
    words := ← c.words.mapM (namedList ev), loc }

/-! ## Pipeline -/

structure ArtefactSpec where
  /-- Constructor name, e.g. `scaledModel`. -/
  name : String
  doc : Option String
  /-- Path relative to the repository root; a trailing `/` marks a directory. -/
  path : String
  isSource : Bool

def ArtefactSpec.isDir (a : ArtefactSpec) : Bool := a.path.endsWith "/"

structure StageSpec where
  name : String
  doc : Option String
  script : String
  /-- Artefact names, from `Stage.reads` and `Stage.writes`. -/
  reads : List String
  writes : List String
  /-- Paths, from `Stage.inputs` and `Stage.outputs`. -/
  inputs : List String
  outputs : List String
  /-- Names of the stages whose scripts this stage's script imports, from
  `Stage.imports`. -/
  imports : List String
  /-- The scripts whose code the stage runs, from `Stage.codeInputs`: its own
  script first. -/
  codeInputs : List String

structure PipelineSpec where
  doc : Option String
  stages : List StageSpec
  artefacts : List ArtefactSpec
  edges : List (String × String)
  edgesDoc : Option String
  topoOrder : List String
  loc : Loc

def PipelineSpec.stage? (p : PipelineSpec) (n : String) : Option StageSpec :=
  p.stages.find? (·.name == n)

def PipelineSpec.artefact? (p : PipelineSpec) (n : String) : Option ArtefactSpec :=
  p.artefacts.find? (·.name == n)

/-- Stages in `topoOrder`. -/
def PipelineSpec.ordered (p : PipelineSpec) : List StageSpec := p.topoOrder.filterMap p.stage?

def pipelineSpec : MetaM PipelineSpec := do
  let ns := `BioMech.Pipeline
  let inNs (t : String) := s!"open {ns} in ({t})"
  let stageTy := ns ++ `Stage
  let artTy := ns ++ `Artefact
  let stageCtors ← ctorNames stageTy
  let artNames ← evalEnumList artTy (inNs "Artefact.all")
  let artDocs ← ctorDocs artTy
  let artVals ← evalTerm (List (String × Bool)) (inNs "Artefact.all.map fun a => (a.path, a.isSource)")
  let artefacts := (artNames.zip artVals).map fun (n, path, src) =>
    { name := n, doc := (artDocs.find? (·.1 == n)).bind (·.2), path, isSource := src : ArtefactSpec }
  let stageIdx ← evalTerm (List Nat) (inNs "Stage.all.map Stage.ctorIdx")
  let vals ← evalTerm (List (String × String × List String × List String))
    (inNs "Stage.all.map fun s => (s.name, s.script, s.inputs, s.outputs)")
  let readsWrites ← evalTerm (List (List Nat × List Nat))
    (inNs "Stage.all.map fun s => (s.reads.map Artefact.ctorIdx, s.writes.map Artefact.ctorIdx)")
  let code ← evalTerm (List (List String × List String))
    (inNs "Stage.all.map fun s => (s.imports.map Stage.name, s.codeInputs)")
  let artCtors ← ctorNames artTy
  let stages ← (((stageIdx.zip vals).zip readsWrites).zip code).mapM
      fun (((i, name, script, inputs, outputs), (r, w)), (imports, codeInputs)) => do
    let ctor ← ctorAt stageCtors stageTy i
    return { name, doc := ← docOf (stageTy ++ ctor.toName), script, inputs, outputs,
             reads := ← r.mapM (ctorAt artCtors artTy), writes := ← w.mapM (ctorAt artCtors artTy),
             imports, codeInputs : StageSpec }
  return {
    doc := ← docOf (ns ++ `Stage), stages, artefacts,
    edges := ← evalTerm (List (String × String)) (inNs "edges.map fun e => (e.1.name, e.2.name)"),
    edgesDoc := ← docOf (ns ++ `edges),
    topoOrder := ← evalTerm (List String) (inNs "topoOrder.map Stage.name"),
    loc := ← locOf (ns ++ `edges) }

/-! ## Components -/

structure ComponentSpec where
  name : String
  doc : Option String
  /-- Paths relative to the repository root; a trailing `/` marks a directory. -/
  paths : List String

structure ComponentsSpec where
  components : List ComponentSpec
  edges : List (String × String)
  edgesDoc : Option String
  topoOrder : List String
  sharedImports : List String
  sharedDoc : Option String
  loc : Loc

def componentsSpec : MetaM ComponentsSpec := do
  let ns := `BioMech.Components
  let inNs (t : String) := s!"open {ns} in ({t})"
  let ty := ns ++ `Component
  let idx ← evalTerm (List Nat) (inNs "Component.all.map Component.ctorIdx")
  let ctors ← ctorNames ty
  let vals ← evalTerm (List (String × List String)) (inNs "Component.all.map fun c => (c.name, c.paths)")
  let components ← (idx.zip vals).mapM fun (i, name, paths) => do
    return { name, paths, doc := ← docOf (ty ++ (← ctorAt ctors ty i).toName) : ComponentSpec }
  return {
    components,
    edges := ← evalTerm (List (String × String)) (inNs "edges.map fun e => (e.1.name, e.2.name)"),
    edgesDoc := ← docOf (ns ++ `edges),
    topoOrder := ← evalTerm (List String) (inNs "topoOrder.map Component.name"),
    sharedImports := ← evalTerm (List String) (inNs "sharedImports"),
    sharedDoc := ← docOf (ns ++ `sharedImports),
    loc := ← locOf (ns ++ `edges) }

/-! ## Theorems -/

structure TheoremSpec where
  /-- Full Lean name, e.g. `BioMech.Gait.strides_accepted`. -/
  name : String
  /-- The namespace the statement is printed in: names inside it print short. -/
  ns : String
  statement : String
  doc : Option String
  loc : Loc

/-- The namespace to print `n`'s statement in: its prefix, minus trailing
components that name types (e.g. `BioMech.Gait` for `BioMech.Gait.GaitPhase.mem_all`). -/
partial def printNs (env : Environment) (n : Name) : Name :=
  let rec up (p : Name) : Name :=
    match p with
    | .str q _ => if env.contains p then up q else p
    | _ => p
  up n.getPrefix

/-- Width of pretty-printed statements, in characters. -/
def statementWidth : Nat := 100

/-- Every theorem declared in `mod`, in source order. Internal and generated
declarations (names with a `_` component, equation lemmas, declarations
without a source range) stay out. -/
def theoremsOf (env : Environment) (mod : Name) : IO (List TheoremSpec) := do
  let some idx := env.getModuleIdx? mod | throw <| IO.userError s!"module {mod} is missing"
  let some data := env.header.moduleData[idx.toNat]? | throw <| IO.userError s!"module {mod} is missing"
  let names := data.constNames.toList.filter fun n =>
    !n.isInternal && !(match n with | .str _ s => s.startsWith "eq_" || s == "eq_def" | _ => false) &&
    (match env.find? n with | some (.thmInfo _) => true | _ => false)
  let specs ← names.filterMapM fun n => do
    let ns := printNs env n
    let ctx : Core.Context := {
      fileName := "<gen>", fileMap := default, maxHeartbeats := 0, currNamespace := ns,
      options := Std.Format.format.width.set {} statementWidth }
    let (r, _, _) ← (show MetaM (Option TheoremSpec) from do
      let some info := (← getEnv).find? n | return none
      let some _ ← findDeclarationRanges? n | return none
      let stmt ← ppExpr info.type
      return some { name := n.toString, ns := ns.toString, statement := stmt.pretty statementWidth,
                    doc := ← docOf n, loc := ← locOf n }).toIO ctx { env }
    return r
  return specs.mergeSort (fun a b => a.loc.line ≤ b.loc.line)

/-! ## Everything -/

structure Model where
  gait : FsmSpec
  ui : FsmSpec
  pipeline : PipelineSpec
  components : ComponentsSpec
  theorems : List TheoremSpec

def loadModel (env : Environment) : IO Model := do
  let (gait, ui, pipeline, components) ← runMeta env do
    return (← fsmSpec gaitConfig, ← fsmSpec uiConfig, ← pipelineSpec, ← componentsSpec)
  let theorems ← specModules.flatMapM (theoremsOf env)
  return { gait, ui, pipeline, components, theorems }

end BioMech.Gen
