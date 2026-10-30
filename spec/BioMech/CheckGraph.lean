import Lean
import Mathlib.Combinatorics.Quiver.Prefunctor
import BioMech.Schema

/-!
# Prefunctor check of `graph.json`

`lake exe checkGraph FILE` reads a `graph.json` (contract C3) and checks that it
is well typed: the data graph carries a prefunctor into the schema quiver
`Kind` (contract C1). It prints a summary and exits 0 on success; it lists
every error and exits 1 otherwise.

## Terms

* *Quiver*: vertices and, between any two vertices, a type of arrows. Graphs
  with parallel arrows and loops are quivers.
* *Prefunctor* `V ⥤q W`: a map of quivers, sending each vertex of `V` to a
  vertex of `W` (`obj`) and each arrow `s ⟶ t` of `V` to an arrow
  `obj s ⟶ obj t` of `W` (`map`).
* *Data quiver* (`DataQuiver g`): the quiver of one `graph.json`. Its vertices
  are the positions in `nodes`; an arrow from `s` to `t` is a position in
  `edges` whose `source` names `s` and whose `target` names `t`.
* *Raw graph* (`RawGraph`): the part of the file the prefunctor speaks about,
  as strings: each node's `id` and `kind`, each edge's `source`, `target`, and
  `relation`.
* *Resolve*: find the node an edge endpoint names, the first node whose `id`
  equals it (`RawGraph.resolve`).
* *Well typed* (`WellTyped g`): every node kind names a `Kind`, and every edge
  resolves both endpoints and names, by its relation, a `SchemaArrow` from the
  source node's kind to the target node's kind.
* *Diagnostics*: the error messages. They name the failing node or edge by its
  position in the file, e.g. `edges[51]`.

## What the checker covers

1. **Typing** (`WellTyped`, decided in `check`). `check_ok_prefunctor` proves
   that success yields a prefunctor `DataQuiver g ⥤q Kind` whose `obj` is each
   node's declared kind and whose `map` is, for each edge, the `SchemaArrow`
   constructor its relation names. The theorem speaks about `RawGraph`, the
   strings above.
2. **Attribute fields** (`fieldErrors`): every `NodeAttrs` field on each node
   and, for each relation that `edgeAttrs` lists, every field of its attribute
   structure on each edge, with its type. The field names and types come from
   the Lean structures by reflection at build time (`schemaStructs`), so a new
   or renamed field in `BioMech.Schema` reaches the checker on the next build.
3. **Unique ids** and **schema version** (`schemaVersion`).

Diagnostics for 1 come from `typeErrors`; the verdict for 1 comes from the
decision of `WellTyped`, the proposition the theorem speaks about. `check`
succeeds when the diagnostics list is empty and `WellTyped` holds.
-/

namespace BioMech.CheckGraph
open Lean Elab Term

/-! ## Reflection of the schema at build time -/

/-- Field types of the attribute structures, as the checker reads them from
JSON. An enumeration carries its short name and its constructor names. -/
inductive FieldTy
  | string | float | nat | int | bool
  | option (t : FieldTy)
  | array (t : FieldTy)
  | enum (name : String) (ctors : List String)
  deriving Repr, Inhabited, ToExpr

/-- Name of a field type in diagnostics, e.g. `Array Float`. -/
def FieldTy.name : FieldTy → String
  | .string => "String" | .float => "Float" | .nat => "Nat" | .int => "Int"
  | .bool => "Bool"
  | .option t => s!"Option {t.name}"
  | .array t => s!"Array {t.name}"
  | .enum n _ => n

/-- The constructors of an enumeration such as `Kind` or `Side`: an inductive
type whose constructors all take zero arguments. -/
def enumCtors? (env : Environment) (n : Name) : Option (List Name) :=
  match env.find? n with
  | some (.inductInfo v) =>
    if v.numParams == 0 && v.numIndices == 0 && v.ctors.all fun c =>
        match env.find? c with
        | some (.ctorInfo cv) => cv.numFields == 0
        | _ => false
    then some v.ctors else none
  | _ => none

/-- The `FieldTy` of a field's Lean type. -/
partial def reflectTy (env : Environment) (e : Expr) : Except String FieldTy :=
  match e.getAppFn, e.getAppArgs with
  | .const ``String _, #[] => .ok .string
  | .const ``Float _, #[] => .ok .float
  | .const ``Nat _, #[] => .ok .nat
  | .const ``Int _, #[] => .ok .int
  | .const ``Bool _, #[] => .ok .bool
  | .const ``Option _, #[t] => return .option (← reflectTy env t)
  | .const ``Array _, #[t] => return .array (← reflectTy env t)
  | .const n _, #[] => match enumCtors? env n with
    | some cs => .ok (.enum n.lastComponentAsString (cs.map (·.lastComponentAsString)))
    | none => .error s!"unsupported field type {n}"
  | _, _ => .error s!"unsupported field type {e}"

/-- The fields of structure `n`, in declaration order, with their types. -/
def reflectFields (env : Environment) (n : Name) : Except String (List (String × FieldTy)) :=
  (getStructureFields env n).toList.mapM fun f => do
    let some info := env.find? (n ++ f) | throw s!"missing projection {n ++ f}"
    return (f.toString, ← reflectTy env info.type.bindingBody!)

/-- `schema_structs%`: every structure declared in `BioMech.Schema`, with its
fields and their types, read from the environment at build time. -/
elab "schema_structs%" : term => do
  let env ← getEnv
  let some idx := env.getModuleIdx? `BioMech.Schema
    | throwError "module BioMech.Schema is missing from the imports"
  let names := (env.header.moduleData[idx.toNat]!).constNames.toList.filter (isStructure env)
  let table ← names.mapM fun n => do
    match reflectFields env n with
    | .ok fs => pure (n, fs)
    | .error e => throwError e
  return toExpr table

/-- `ctor_table% T`: the list `[("c", T.c), …]` over the constructors of `T`,
in declaration order. For an indexed family such as `SchemaArrow`, each entry
packs the constructor with its indices, `("c", ⟨_, _, T.c⟩)`. -/
elab "ctor_table% " id:ident : term <= expected => do
  let n ← realizeGlobalConstNoOverloadWithInfo id
  let some (.inductInfo v) := (← getEnv).find? n | throwError "{n} needs to be an inductive type"
  let items ← v.ctors.toArray.mapM fun c => do
    let s := Syntax.mkStrLit c.lastComponentAsString
    if v.numIndices == 2 then `(($s, ⟨_, _, $(mkCIdent c)⟩)) else `(($s, $(mkCIdent c)))
  elabTerm (← `([$items,*])) expected

/-! ## The schema as the checker sees it -/

/-- Every structure of `BioMech.Schema` with its fields, from `schema_structs%`. -/
def schemaStructs : List (Name × List (String × FieldTy)) := schema_structs%

/-- Constructor names of `Kind`, from `ctor_table%`. -/
def kindTable : List (String × Kind) := ctor_table% Kind

/-- Constructor names of `SchemaArrow`, each with its arrow, from `ctor_table%`. -/
def arrowTable : List (String × Σ a b : Kind, SchemaArrow a b) := ctor_table% SchemaArrow

/-- `arrowTable` lists the arrows of `SchemaArrow.all`, in the same order. -/
theorem arrowTable_arrows : arrowTable.map (·.2) = SchemaArrow.all := rfl

/-- The `Kind` a string names. -/
def kindOf? (s : String) : Option Kind := kindTable.lookup s

/-- The schema arrow a relation names, with its source and target kinds. -/
def arrowOf? (s : String) : Option (Σ a b : Kind, SchemaArrow a b) := arrowTable.lookup s

/-- The string that names a `Kind`. -/
def kindName (k : Kind) : String := ((kindTable.find? (·.2 == k)).map (·.1)).getD "?"

/-- Fields of `NodeAttrs`. -/
def nodeFields : List (String × FieldTy) := (schemaStructs.lookup ``NodeAttrs).getD []

/-- Fields a relation's edges carry beyond `source`, `target`, `relation`: those
of the attribute structure `edgeAttrs` assigns to it, and the empty list for
every other relation. -/
def edgeFields (relation : String) : List (String × FieldTy) :=
  match edgeAttrs.find? (·.1.lastComponentAsString == relation) with
  | some (_, s) => (schemaStructs.lookup s).getD []
  | none => []

-- Every structure `edgeAttrs` names is in `schemaStructs`, and so is `NodeAttrs`.
#guard (``NodeAttrs :: edgeAttrs.map (·.2)).all fun s => (schemaStructs.lookup s).isSome

/-! ## The raw graph and its quiver -/

/-- One node, as strings: its `id` and its `kind`. -/
structure RawNode where
  id : String
  kind : String

/-- One edge, as strings: its endpoints' ids and its relation. -/
structure RawEdge where
  source : String
  target : String
  relation : String

/-- The part of `graph.json` the prefunctor speaks about. Positions match the
file's `nodes` and `edges` arrays. -/
structure RawGraph where
  nodes : Array RawNode
  edges : Array RawEdge

/-- The node an endpoint id names: the first node with that `id`. -/
def RawGraph.resolve (g : RawGraph) (id : String) : Option (Fin g.nodes.size) :=
  g.nodes.findFinIdx? (·.id == id)

/-- Edge `e` is well typed in `g`: both endpoints resolve, and its relation
names a schema arrow from the source node's kind to the target node's kind. -/
def EdgeTyped (g : RawGraph) (e : RawEdge) : Prop :=
  match g.resolve e.source, g.resolve e.target, arrowOf? e.relation with
  | some s, some t, some a =>
    kindOf? g.nodes[s].kind = some a.1 ∧ kindOf? g.nodes[t].kind = some a.2.1
  | _, _, _ => False

instance (g : RawGraph) (e : RawEdge) : Decidable (EdgeTyped g e) := by
  unfold EdgeTyped; split <;> infer_instance

/-- The graph is well typed: every node's kind names a `Kind`, and every edge
is well typed. -/
def WellTyped (g : RawGraph) : Prop :=
  (∀ v : Fin g.nodes.size, (kindOf? g.nodes[v].kind).isSome) ∧
    ∀ i : Fin g.edges.size, EdgeTyped g g.edges[i]

instance (g : RawGraph) : Decidable (WellTyped g) := by
  unfold WellTyped; infer_instance

/-- Vertices of the data quiver of `g`: positions in `g.nodes`. -/
structure DataQuiver (g : RawGraph) where
  idx : Fin g.nodes.size

/-- Arrows of the data quiver: an arrow from `s` to `t` is a position in
`g.edges` whose source resolves to `s` and whose target resolves to `t`. -/
instance (g : RawGraph) : Quiver (DataQuiver g) where
  Hom s t := {i : Fin g.edges.size //
    g.resolve g.edges[i].source = some s.idx ∧ g.resolve g.edges[i].target = some t.idx}

/-- The declared kind of a vertex of a well typed graph. -/
def kindAt {g : RawGraph} (h : WellTyped g) (v : DataQuiver g) : Kind :=
  (kindOf? g.nodes[v.idx].kind).get (h.1 v.idx)

/-- Each arrow of the data quiver of a well typed graph names, by its relation, a
schema arrow between the kinds of its endpoints. -/
theorem exists_schemaArrow {g : RawGraph} (h : WellTyped g) {s t : DataQuiver g} (e : s ⟶ t) :
    ∃ x : SchemaArrow (kindAt h s) (kindAt h t),
      arrowOf? g.edges[e.1].relation = some ⟨_, _, x⟩ := by
  obtain ⟨i, hs, ht⟩ := e
  have hi := h.2 i
  unfold EdgeTyped at hi
  rw [hs, ht] at hi
  dsimp only
  revert hi
  cases ha : arrowOf? g.edges[i].relation with
  | none => simp
  | some a =>
    obtain ⟨a1, a2, x⟩ := a
    rintro ⟨h1, h2⟩
    have e1 : kindAt h s = a1 := Option.some.inj (by rw [kindAt, Option.some_get]; exact h1)
    have e2 : kindAt h t = a2 := Option.some.inj (by rw [kindAt, Option.some_get]; exact h2)
    rw [e1, e2]
    exact ⟨x, rfl⟩

/-- **A well typed graph carries a prefunctor into the schema quiver.** Its
`obj` sends each node to the `Kind` its `kind` field names, and its `map` sends
each edge to the `SchemaArrow` constructor its `relation` field names. -/
theorem prefunctor_of_wellTyped {g : RawGraph} (h : WellTyped g) :
    ∃ F : DataQuiver g ⥤q Kind,
      (∀ v, kindOf? g.nodes[v.idx].kind = some (F.obj v)) ∧
      ∀ {s t : DataQuiver g} (e : s ⟶ t), arrowOf? g.edges[e.1].relation = some ⟨_, _, F.map e⟩ :=
  ⟨{ obj := kindAt h, map := fun e => Classical.choose (exists_schemaArrow h e) },
   fun v => by simp [kindAt], fun e => Classical.choose_spec (exists_schemaArrow h e)⟩

/-! ## Reading the JSON -/

/-- Position of node `i` in diagnostics. -/
def nodeAt (i : Nat) : String := s!"nodes[{i}]"

/-- Position and id of node `i` in diagnostics, e.g. `nodes[0] bone:pelvis`. -/
def nodeLabel (i : Nat) (id : String) : String := s!"nodes[{i}] {id}"

/-- Position and label of edge `i` in diagnostics, e.g.
`edges[3]: muscle:glmax1_r —crosses→ joint:hip_r`. -/
def edgeAt (i : Nat) (e : RawEdge) : String :=
  s!"edges[{i}]: {e.source} —{e.relation}→ {e.target}"

/-- Errors of a JSON value against a field type. `path` names the value within
its object, e.g. `activation[2]`. -/
def tyErrors (path : String) : FieldTy → Json → Array String
  | .option _, .null => #[]
  | .option t, v => tyErrors path t v
  | .array t, .arr xs => (xs.mapIdx fun k x => tyErrors s!"{path}[{k}]" t x).flatten
  | .enum n cs, .str s =>
    if cs.contains s then #[] else #[s!"field {path}: unknown {n} \"{s}\", expected one of {cs}"]
  | .string, .str _ | .float, .num _ | .int, .num ⟨_, 0⟩ | .bool, .bool _ => #[]
  | .nat, .num ⟨m, 0⟩ => if m ≥ 0 then #[] else #[s!"field {path}: expected Nat, got {m}"]
  | t, v => #[s!"field {path}: expected {t.name}, got {v.compress}"]

/-- Errors of a JSON object against a list of fields: each missing or mistyped
field, prefixed by `at_`, the object's position and label. -/
def fieldErrors (at_ : String) (fields : List (String × FieldTy)) (obj : Json) : Array String :=
  fields.toArray.flatMap fun (f, ty) =>
    match obj.getObjVal? f with
    | .ok v => (tyErrors f ty v).map (s!"{at_}: " ++ ·)
    | .error _ => #[s!"{at_}: missing field {f}"]

/-- The string at key `f`, or `""` when it is missing or holds another type
(`fieldErrors` reports those). -/
def strField (obj : Json) (f : String) : String :=
  (obj.getObjValAs? String f).toOption.getD ""

/-- The common edge fields, all strings. -/
def edgeBaseFields : List (String × FieldTy) :=
  [("source", .string), ("target", .string), ("relation", .string)]

/-- Reads the raw graph from the JSON and collects the errors of everything
outside typing: top-level shape, schema version, and attribute fields. -/
def parse (j : Json) : RawGraph × Array String := Id.run do
  let mut errs := #[]
  match j.getObjValAs? Nat "schemaVersion" with
  | .ok v => if v != schemaVersion then
      errs := errs.push s!"schemaVersion: expected {schemaVersion}, got {v}"
  | .error _ => errs := errs.push s!"schemaVersion: expected the Nat {schemaVersion}"
  let arr? (k : String) : Option (Array Json) := (j.getObjVal? k).toOption.bind (·.getArr?.toOption)
  for k in ["nodes", "edges"] do
    if (arr? k).isNone then errs := errs.push s!"graph: expected an array `{k}`"
  let nodesJ := (arr? "nodes").getD #[]
  let edgesJ := (arr? "edges").getD #[]
  let mut nodes := #[]
  for h : i in [:nodesJ.size] do
    let n := nodesJ[i]
    errs := errs ++ fieldErrors (nodeLabel i (strField n "id")) nodeFields n
    nodes := nodes.push { id := strField n "id", kind := strField n "kind" }
  let mut edges := #[]
  for h : i in [:edgesJ.size] do
    let o := edgesJ[i]
    let e : RawEdge :=
      { source := strField o "source", target := strField o "target",
        relation := strField o "relation" }
    errs := errs ++ fieldErrors (edgeAt i e) (edgeBaseFields ++ edgeFields e.relation) o
    edges := edges.push e
  return ({ nodes, edges }, errs)

/-! ## Typing diagnostics -/

/-- Diagnostics for typing: duplicate ids, unknown relations, unknown node ids,
and edges whose endpoint kinds lack the arrow their relation names. Unknown
kinds are reported by `fieldErrors` (the `kind` field is an enumeration). -/
def typeErrors (g : RawGraph) : Array String := Id.run do
  let mut errs := #[]
  let mut seen : Std.HashMap String Nat := {}
  for h : i in [:g.nodes.size] do
    let id := g.nodes[i].id
    match seen[id]? with
    | some j => errs := errs.push s!"{nodeAt i}: duplicate id {id}, first at {nodeAt j}"
    | none => seen := seen.insert id i
  for h : i in [:g.edges.size] do
    let e := g.edges[i]
    let at_ := edgeAt i e
    let arrow := arrowOf? e.relation
    if arrow.isNone then errs := errs.push s!"{at_}: unknown relation \"{e.relation}\""
    let s := g.resolve e.source
    let t := g.resolve e.target
    if s.isNone then errs := errs.push s!"{at_}: unknown node id {e.source} (source)"
    if t.isNone then errs := errs.push s!"{at_}: unknown node id {e.target} (target)"
    match s, t, arrow with
    | some s, some t, some ⟨a, b, _⟩ =>
      match kindOf? g.nodes[s].kind, kindOf? g.nodes[t].kind with
      | some ks, some kt =>
        if ks != a || kt != b then
          errs := errs.push (s!"{at_}: {e.relation} needs {kindName a} → {kindName b}, " ++
            s!"got {kindName ks} → {kindName kt}")
      | _, _ => pure ()
    | _, _, _ => pure ()
  return errs

/-! ## The check -/

/-- The check: parse, collect diagnostics, and decide `WellTyped`. Success
returns the parsed raw graph. -/
def check (j : Json) : Except (Array String) RawGraph :=
  let r := parse j
  let errs := r.2 ++ typeErrors r.1
  if errs.isEmpty ∧ WellTyped r.1 then .ok r.1
  else if errs.isEmpty then .error #["internal: the diagnostics list is empty, yet the graph is ill typed"]
  else .error errs

/-- Success returns the graph `parse` reads from the file, and it is well typed. -/
theorem check_ok {j : Json} {g : RawGraph} (h : check j = .ok g) :
    g = (parse j).1 ∧ WellTyped g := by
  unfold check at h
  dsimp only at h
  split at h
  · cases h; exact ⟨rfl, (by assumption : _ ∧ _).2⟩
  · split at h <;> cases h

/-- **Success yields the prefunctor.** When `check` accepts a file, the raw graph
read from it carries a prefunctor `DataQuiver g ⥤q Kind` that sends each node to
its declared kind and each edge to the schema arrow its relation names. The
theorem covers the typing of nodes and edges; attribute fields, unique ids, and
the schema version are checked by the diagnostics alone. -/
theorem check_ok_prefunctor {j : Json} {g : RawGraph} (h : check j = .ok g) :
    g = (parse j).1 ∧ ∃ F : DataQuiver g ⥤q Kind,
      (∀ v, kindOf? g.nodes[v.idx].kind = some (F.obj v)) ∧
      ∀ {s t : DataQuiver g} (e : s ⟶ t), arrowOf? g.edges[e.1].relation = some ⟨_, _, F.map e⟩ :=
  ⟨(check_ok h).1, prefunctor_of_wellTyped (check_ok h).2⟩

/-- Summary of a well typed graph: node count per kind and edge count per
relation, in constructor order. -/
def summary (g : RawGraph) : List String :=
  let kinds := kindTable.filterMap fun (k, _) =>
    let n := (g.nodes.filter (·.kind == k)).size
    if n == 0 then none else some s!"  {k}: {n}"
  let rels := arrowTable.filterMap fun (r, _) =>
    let n := (g.edges.filter (·.relation == r)).size
    if n == 0 then none else some s!"  {r}: {n}"
  [s!"{g.nodes.size} nodes"] ++ kinds ++ [s!"{g.edges.size} edges"] ++ rels

end BioMech.CheckGraph

open BioMech.CheckGraph in
/-- `lake exe checkGraph FILE`: exit 0 with a summary when the file is well
typed, exit 1 with every error otherwise, exit 2 on a usage error. -/
def main (args : List String) : IO UInt32 := do
  let [path] := args | IO.eprintln "usage: lake exe checkGraph FILE"; return 2
  let text ← try IO.FS.readFile path catch e => IO.eprintln s!"{path}: {e}"; return 1
  match Lean.Json.parse text with
  | .error e => IO.println s!"{path}: invalid JSON: {e}"; return 1
  | .ok j =>
    match check j with
    | .ok g =>
      IO.println s!"{path}: well typed (prefunctor into Kind)"
      for l in summary g do IO.println l
      return 0
    | .error errs =>
      for l in errs do IO.println l
      IO.println s!"{path}: {errs.size} error(s)"
      return 1
