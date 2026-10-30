import BioMech.Gen.ArchJson

/-!
# Diagram emitters: `generated/diagrams/*.mmd` (Mermaid) and `*.dot` (Graphviz)

Five diagrams, each in both languages:

* `schema`: the schema quiver; kinds as nodes, relations as labelled edges (with
  the attribute structure, when the relation carries one).
* `gaitFsm`, `uiFsm`: the explicit rows of each DFA; a note states the implicit
  rule for absent pairs. The start state has an incoming arrow from a point;
  accept states have a heavy border (Mermaid) or a double circle (DOT).
* `pipeline`: stages in `topoOrder`, edges labelled with the artefacts the
  source writes and the target reads.
* `components`: components in `topoOrder` (importers first), edges from
  importer to imported.

Mermaid flowchart node ids carry the prefix `n_`, which keeps them clear of
Mermaid keywords such as `end`.
-/

namespace BioMech.Gen

/-- A label without backticks, for diagram text. -/
def plain (s : String) : String := s.replace "`" ""

def mmdLabel (s : String) : String := "\"" ++ (plain s).replace "\"" "#quot;" ++ "\""
def mmdId (s : String) : String := "n_" ++ s

structure Graph where
  name : String
  source : String
  /-- Node ids with labels. -/
  nodes : List (String × String)
  /-- Edges with an optional label. -/
  edges : List (String × String × Option String)
  /-- Mermaid flowchart direction and Graphviz `rankdir`. -/
  dir : String

def Graph.mermaid (g : Graph) : String :=
  let lines :=
    [s!"%% {headerText g.source}", s!"flowchart {g.dir}"] ++
    g.nodes.map (fun (n, l) => s!"  {mmdId n}[{mmdLabel l}]") ++
    g.edges.map fun (a, b, l) => match l with
      | some l => s!"  {mmdId a} -->|{mmdLabel l}| {mmdId b}"
      | none => s!"  {mmdId a} --> {mmdId b}"
  "\n".intercalate lines ++ "\n"

def Graph.dot (g : Graph) : String :=
  let lines :=
    [s!"// {headerText g.source}", s!"digraph {g.name} \{",
     s!"  rankdir={g.dir};", "  node [shape=box, fontname=\"Helvetica\"];",
     "  edge [fontname=\"Helvetica\", fontsize=10];"] ++
    g.nodes.map (fun (n, l) => s!"  {jsonQuote n} [label={jsonQuote (plain l)}];") ++
    g.edges.map (fun (a, b, l) => match l with
      | some l => s!"  {jsonQuote a} -> {jsonQuote b} [label={jsonQuote (plain l)}];"
      | none => s!"  {jsonQuote a} -> {jsonQuote b};") ++ ["}"]
  "\n".intercalate lines ++ "\n"

def schemaGraph (s : SchemaSpec) (kinds : List Item) (loc : Loc) : Graph where
  name := "schema"
  source := loc.file
  nodes := kinds.map fun k => (k.name, k.name)
  edges := s.arrows.map fun a =>
    (a.source, a.target, some (match a.attrs with | some t => s!"{a.name} · {t}" | none => a.name))
  dir := "LR"

def pipelineGraph (p : PipelineSpec) : Graph where
  name := "pipeline"
  source := p.loc.file
  nodes := p.topoOrder.map fun n => (n, n)
  edges := p.edges.map fun (a, b) =>
    (a, b, match p.passed a b with | [] => none | xs => some (", ".intercalate xs))
  dir := "TB"

def componentsGraph (c : ComponentsSpec) : Graph where
  name := "components"
  source := c.loc.file
  nodes := c.topoOrder.map fun n => (n, n)
  edges := c.edges.map fun (a, b) => (a, b, none)
  dir := "TB"

def fsmMermaid (f : FsmSpec) : String :=
  let noteAt := match f.implicit with | .sink s => s | _ => f.start
  let lines :=
    [s!"%% {headerText f.source}", "stateDiagram-v2", "  direction LR"] ++
    f.states.map (fun s => s!"  {s.name}") ++
    [s!"  [*] --> {f.start}"] ++
    f.rows.map (fun (a, e, b) => s!"  {a} --> {b} : {e}") ++
    [s!"  note right of {noteAt} : {plain f.implicit.describe}",
     "  classDef accept stroke-width:3px",
     s!"  class {",".intercalate f.accept} accept"]
  "\n".intercalate lines ++ "\n"

def fsmDot (f : FsmSpec) : String :=
  let lines :=
    [s!"// {headerText f.source}", s!"digraph {f.config.id} \{", "  rankdir=LR;",
     "  node [shape=ellipse, fontname=\"Helvetica\"];",
     "  edge [fontname=\"Helvetica\", fontsize=10];",
     s!"  label={jsonQuote (plain f.implicit.describe)};", "  labelloc=b;",
     "  __start [shape=point, label=\"\"];"] ++
    f.states.map (fun s =>
      let shape := if f.accept.contains s.name then " [shape=doublecircle]" else ""
      s!"  {jsonQuote s.name}{shape};") ++
    [s!"  __start -> {jsonQuote f.start};"] ++
    f.rows.map (fun (a, e, b) => s!"  {jsonQuote a} -> {jsonQuote b} [label={jsonQuote e}];") ++ ["}"]
  "\n".intercalate lines ++ "\n"

/-- Every diagram file, relative to the repository root. -/
def diagrams (s : SchemaSpec) (kinds : List Item) (kindLoc : Loc) (m : Model) : List (String × String) :=
  let graphs := [schemaGraph s kinds kindLoc, pipelineGraph m.pipeline, componentsGraph m.components]
  let fsms := [m.gait, m.ui]
  let path (n ext : String) := s!"generated/diagrams/{n}.{ext}"
  graphs.flatMap (fun g => [(path g.name "mmd", g.mermaid), (path g.name "dot", g.dot)]) ++
  fsms.flatMap fun f => [(path f.config.id "mmd", fsmMermaid f), (path f.config.id "dot", fsmDot f)]

end BioMech.Gen
