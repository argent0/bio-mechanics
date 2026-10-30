import BioMech.Gen.Reflect
import BioMech.Gen.Fsm

/-!
# Architecture model emitter: `generated/architecture.json`

The model the `/architecture` page draws. This docstring is the source of
truth for the JSON shape; `archVersion` changes with any change to it.

## Shape

Objects keep their keys in the order listed; arrays keep source order. `doc`
fields hold a Lean docstring or `null`. `Loc` is
`{ "module", "file", "line", "startLine", "endLine" }`: the Lean module, its
source file relative to the repository root, the line of the declaration's
name, and its first (docstring included) and last lines, all 1-based.

```
{
  "$generated": string,                    // header line
  "archVersion": 1,
  "schema": {                              // the schema quiver (BioMech.Schema)
    "graphSchemaVersion": number,          // schemaVersion of graph.json
    "loc": Loc,                            // of `Kind`
    "kinds": [{ "name", "doc" }],          // the quiver's vertices
    "arrows": [{ "name", "source", "target", "attrs": string | null }],
    "structs": [{ "name", "doc", "fields": [{ "name", "type", "doc" }] }],
    "enums": [{ "name", "doc", "values": [string] }]
  },
  "fsms": [                                // gait DFA, then UI DFA
    { "id": "gaitFsm" | "uiFsm",
      "module", "loc": Loc,                // loc of the state type
      "stateType", "eventType", "stateDoc", "eventDoc",
      "states": [{ "name", "doc" }],       // order of the Lean `all` list
      "events": [{ "name", "doc" }],
      "start": string,
      "accept": [string],
      "transitions": [{ "from", "event", "to" }],   // explicit rows
      "implicit": { "kind": "sink" | "selfLoop" | "mixed", "state": string | null },
      "table": [{ "from", "to": [string] }],         // `to[i]` = step from events[i]
      "stateLists": [{ "name", "doc", "values": [string] }],   // e.g. GaitPhase.phases
      "words": [{ "name", "doc", "events": [string] }] }        // e.g. strideWord
  ],
  "pipeline": {                            // BioMech.Pipeline
    "loc": Loc,                            // of `edges`
    "stages": [{ "name", "doc", "script", "module",
                 "reads": [artefact name], "writes": [artefact name],
                 "inputs": [path], "outputs": [path] }],
    "edges": [{ "source", "target", "artefacts": [artefact name] }],  // writes ∩ reads
    "topoOrder": [stage name],
    "artefacts": [{ "name", "doc", "path", "isSource": bool, "isDirectory": bool }]
  },
  "components": {                          // BioMech.Components
    "loc": Loc,                            // of `edges`
    "components": [{ "name", "doc", "paths": [string] }],
    "edges": [{ "source", "target" }],     // `source` may import `target`
    "topoOrder": [component name],         // importers first
    "sharedImports": [string]
  },
  "theorems": [{ "name", "namespace", "statement", "doc", "loc": Loc }]
}
```

`theorems` lists every theorem declared in `specModules`, by module in that
order, then by line. `name` is the full Lean name; `statement` is the theorem's
type pretty-printed inside `namespace` (names inside it print short), wrapped
at `statementWidth` characters with newlines.
-/

namespace BioMech.Gen

/-- Version of the `architecture.json` shape. -/
def archVersion : Nat := 1

def J.ofLoc (l : Loc) : J :=
  .obj [("module", .str l.module), ("file", .str l.file), ("line", .num l.line),
        ("startLine", .num l.startLine), ("endLine", .num l.endLine)]

def J.ofItem (i : Item) : J := .obj [("name", .str i.name), ("doc", .ofOpt i.doc)]

/-- A field type as Lean spells it, e.g. `Option String`, `Array Float`. -/
def fieldTyText : FieldTy → String
  | .string => "String" | .float => "Float" | .nat => "Nat" | .int => "Int" | .bool => "Bool"
  | .option t => s!"Option {paren t (fieldTyText t)}"
  | .array t => s!"Array {paren t (fieldTyText t)}"
  | .enum n => n
where paren : FieldTy → String → String
  | .option _, s | .array _, s => s!"({s})"
  | _, s => s

def schemaJson (s : SchemaSpec) (kinds : List Item) (loc : Loc) : J :=
  .obj [
    ("graphSchemaVersion", .num s.version),
    ("loc", .ofLoc loc),
    ("kinds", .arr (kinds.map .ofItem)),
    ("arrows", .arr (s.arrows.map fun a => .obj [("name", .str a.name), ("source", .str a.source),
      ("target", .str a.target), ("attrs", .ofOpt a.attrs)])),
    ("structs", .arr (s.structs.map fun st => .obj [("name", .str st.name), ("doc", .ofOpt st.doc),
      ("fields", .arr (st.fields.map fun f => .obj [("name", .str f.name),
        ("type", .str (fieldTyText f.ty)), ("doc", .ofOpt f.doc)]))])),
    ("enums", .arr (s.enums.map fun e => .obj [("name", .str e.name), ("doc", .ofOpt e.doc),
      ("values", J.strs e.ctors)]))]

def fsmJson (f : FsmSpec) : J :=
  let named (key : String) (l : NamedList) : J :=
    .obj [("name", .str l.lean), ("doc", .ofOpt l.doc), (key, J.strs l.values)]
  .obj [
    ("id", .str f.config.id), ("module", .str f.module), ("loc", .ofLoc f.loc),
    ("stateType", .str f.config.state), ("eventType", .str f.config.event),
    ("stateDoc", .ofOpt f.stateDoc), ("eventDoc", .ofOpt f.eventDoc),
    ("states", .arr (f.states.map .ofItem)), ("events", .arr (f.events.map .ofItem)),
    ("start", .str f.start), ("accept", J.strs f.accept),
    ("transitions", .arr (f.rows.map fun (a, e, b) =>
      .obj [("from", .str a), ("event", .str e), ("to", .str b)])),
    ("implicit", .obj [("kind", .str f.implicit.label),
      ("state", match f.implicit with | .sink s => .str s | _ => .null)]),
    ("table", .arr (f.table.map fun (s, ts) => .obj [("from", .str s), ("to", J.strs ts)])),
    ("stateLists", .arr (f.stateLists.map (named "values"))),
    ("words", .arr (f.words.map (named "events")))]

/-- Artefacts that stage `a` writes and stage `b` reads. -/
def PipelineSpec.passed (p : PipelineSpec) (a b : String) : List String :=
  match p.stage? a, p.stage? b with
  | some sa, some sb => sa.writes.filter (sb.reads.contains ·)
  | _, _ => []

def pipelineJson (p : PipelineSpec) : J :=
  .obj [
    ("loc", .ofLoc p.loc),
    ("stages", .arr (p.stages.map fun s => .obj [("name", .str s.name), ("doc", .ofOpt s.doc),
      ("script", .str s.script), ("module", .str (pyModuleOf s.script)),
      ("reads", J.strs s.reads), ("writes", J.strs s.writes),
      ("inputs", J.strs s.inputs), ("outputs", J.strs s.outputs)])),
    ("edges", .arr (p.edges.map fun (a, b) =>
      .obj [("source", .str a), ("target", .str b), ("artefacts", J.strs (p.passed a b))])),
    ("topoOrder", J.strs p.topoOrder),
    ("artefacts", .arr (p.artefacts.map fun a => .obj [("name", .str a.name), ("doc", .ofOpt a.doc),
      ("path", .str a.path), ("isSource", .bool a.isSource), ("isDirectory", .bool a.isDir)]))]

def componentsJson (c : ComponentsSpec) : J :=
  .obj [
    ("loc", .ofLoc c.loc),
    ("components", .arr (c.components.map fun x =>
      .obj [("name", .str x.name), ("doc", .ofOpt x.doc), ("paths", J.strs x.paths)])),
    ("edges", .arr (c.edges.map fun (a, b) => .obj [("source", .str a), ("target", .str b)])),
    ("topoOrder", J.strs c.topoOrder),
    ("sharedImports", J.strs c.sharedImports)]

def theoremJson (t : TheoremSpec) : J :=
  .obj [("name", .str t.name), ("namespace", .str t.ns), ("statement", .str t.statement),
        ("doc", .ofOpt t.doc), ("loc", .ofLoc t.loc)]

/-- Kinds of the schema quiver with their constructor docstrings, and the
location of `Kind`. -/
def schemaKinds (env : Lean.Environment) : IO (List Item × Loc) :=
  runMeta env do
    let docs ← ctorDocs `BioMech.Kind
    return (docs.map fun (n, d) => { name := n, doc := d }, ← locOf `BioMech.Kind)

def architectureJson (s : SchemaSpec) (kinds : List Item) (kindLoc : Loc) (m : Model) : String :=
  let j : J := .obj [
    ("$generated", .str (headerText (", ".intercalate (specModules.map moduleFile)))),
    ("archVersion", .num archVersion),
    ("schema", schemaJson s kinds kindLoc),
    ("fsms", .arr [fsmJson m.gait, fsmJson m.ui]),
    ("pipeline", pipelineJson m.pipeline),
    ("components", componentsJson m.components),
    ("theorems", .arr (m.theorems.map theoremJson))]
  j.render ++ "\n"

end BioMech.Gen
