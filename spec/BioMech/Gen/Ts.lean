import BioMech.Gen.Reflect

/-!
# TypeScript emitter: `generated/ts/types.ts`

Enumerations become string-literal unions with a matching `const` array;
attribute structures become interfaces; `Edge` is a union over relations, each
member holding `source`, `target`, `relation` and the relation's attribute fields.
-/

namespace BioMech.Gen

def tsTy : FieldTy → String
  | .string => "string"
  | .float | .nat | .int => "number"
  | .bool => "boolean"
  | .option t => s!"{tsTy t} | null"
  | .array t => match t with
    | .option _ => s!"({tsTy t})[]"
    | _ => s!"{tsTy t}[]"
  | .enum n _ => n

def tsDoc (indent : String) : Option String → List String
  | none => []
  | some d => [s!"{indent}/** {d.replace "\n" s!"\n{indent} * "} */"]

def quote (s : String) : String := "\"" ++ s ++ "\""

def tsEnum (e : EnumSpec) : List String :=
  let consts := e.name.toUpper
  tsDoc "" e.doc ++
  [s!"export type {e.name} = {" | ".intercalate (e.ctors.map quote)};",
   s!"export const {consts}: readonly {e.name}[] = [{", ".intercalate (e.ctors.map quote)}] as const;", ""]

def tsStruct (s : StructSpec) : List String :=
  tsDoc "" s.doc ++ [s!"export interface {s.name} " ++ "{"] ++
  s.fields.flatMap (fun f => tsDoc "  " f.doc ++ [s!"  {f.name}: {tsTy f.ty};"]) ++ ["}", ""]

def tsTypes (s : SchemaSpec) : String :=
  let arrowEntry (a : ArrowSpec) := s!"  {a.name}: \{ source: {quote a.source}, target: {quote a.target} },"
  let edgeMember (a : ArrowSpec) :=
    let base := s!"EdgeBase<{quote a.name}>"
    "  | " ++ (match a.attrs with | some t => s!"({base} & {t})" | none => base)
  let lines :=
    [s!"// {headerText "spec/BioMech/Schema.lean"}", ""] ++
    [s!"export const SCHEMA_VERSION = {s.version};", ""] ++
    s.enums.flatMap tsEnum ++
    s.structs.flatMap tsStruct ++
    ["/** Arrows of the schema quiver: each relation with its source and target kinds. */",
     s!"export type Relation = {" | ".intercalate (s.arrows.map (quote ·.name))};",
     "export const RELATIONS: { readonly [R in Relation]: { readonly source: Kind; readonly target: Kind } } = {"] ++
    s.arrows.map arrowEntry ++ ["};", "",
     "/** Fields every edge carries. `source` and `target` are node ids. */",
     "export interface EdgeBase<R extends Relation> {", "  source: string;", "  target: string;",
     "  relation: R;", "}", "",
     "/** An edge: the common fields plus the attribute fields of its relation. */",
     "export type Edge ="] ++ s.arrows.map edgeMember ++ ["  ;", "",
     "export type Node = NodeAttrs;", "",
     "/** The shape of `graph.json`. */",
     "export interface Graph {", "  schemaVersion: typeof SCHEMA_VERSION;", "  nodes: Node[];",
     "  edges: Edge[];", "}"]
  "\n".intercalate lines ++ "\n"

end BioMech.Gen
