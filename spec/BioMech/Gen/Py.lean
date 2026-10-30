import BioMech.Gen.Reflect

/-!
# Python emitter: `generated/py/schema.py`

Enumerations become `Literal` aliases with a tuple of values; attribute
structures become `TypedDict`s; each relation gets an edge `TypedDict`.
The module also carries the field table `FIELDS` and `validate_graph`, which
checks a parsed `graph.json` against it: field types, unique node ids, edge
endpoints present, and endpoint kinds matching the relation's schema arrow.
-/

namespace BioMech.Gen

def pyTy : FieldTy → String
  | .string => "str"
  | .float => "float"
  | .nat | .int => "int"
  | .bool => "bool"
  | .option t => s!"{pyTy t} | None"
  | .array t => s!"list[{pyTy t}]"
  | .enum n _ => n

/-- The field type as a Python literal for `FIELDS`. -/
def pySpec : FieldTy → String
  | .string => "\"str\"" | .float => "\"float\"" | .nat => "\"nat\"" | .int => "\"int\""
  | .bool => "\"bool\""
  | .option t => s!"(\"option\", {pySpec t})"
  | .array t => s!"(\"array\", {pySpec t})"
  | .enum n _ => s!"(\"enum\", \"{n}\")"

def pyDoc (indent : String) : Option String → List String
  | none => []
  | some d => [s!"{indent}\"\"\"{d}\"\"\""]

def pq (s : String) : String := "\"" ++ s ++ "\""

def capitalize (s : String) : String :=
  match s.toList with
  | c :: cs => String.ofList (c.toUpper :: cs)
  | [] => s

def edgeClass (a : ArrowSpec) : String := capitalize a.name ++ "Edge"

def pyValidator : List String := [
  "def _check(spec: FieldSpec, value: object, where: str, errors: list[str]) -> None:",
  "    if isinstance(spec, tuple):",
  "        tag, inner = spec",
  "        if tag == \"option\":",
  "            if value is not None:",
  "                _check(inner, value, where, errors)",
  "        elif tag == \"array\":",
  "            if not isinstance(value, list):",
  "                errors.append(f\"{where}: expected a list\")",
  "            else:",
  "                for i, item in enumerate(value):",
  "                    _check(inner, item, f\"{where}[{i}]\", errors)",
  "        elif tag == \"enum\":",
  "            assert isinstance(inner, str)",
  "            if value not in ENUMS[inner]:",
  "                errors.append(f\"{where}: {value!r} is outside {inner}\")",
  "        return",
  "    ok = {",
  "        \"str\": isinstance(value, str),",
  "        \"bool\": isinstance(value, bool),",
  "        \"float\": isinstance(value, (int, float)) and not isinstance(value, bool),",
  "        \"int\": isinstance(value, int) and not isinstance(value, bool),",
  "        \"nat\": isinstance(value, int) and not isinstance(value, bool) and value >= 0,",
  "    }[spec]",
  "    if not ok:",
  "        errors.append(f\"{where}: expected {spec}, got {value!r}\")",
  "",
  "",
  "def _check_fields(struct: str, obj: dict[str, object], where: str, errors: list[str]) -> None:",
  "    for name, spec in FIELDS[struct].items():",
  "        if name not in obj:",
  "            errors.append(f\"{where}: missing field {name}\")",
  "        else:",
  "            _check(spec, obj[name], f\"{where}.{name}\", errors)",
  "",
  "",
  "def validate_graph(graph: object) -> list[str]:",
  "    \"\"\"Errors in a parsed `graph.json`; an empty list means the graph is well typed.\"\"\"",
  "    errors: list[str] = []",
  "    if not isinstance(graph, dict):",
  "        return [\"graph: expected an object\"]",
  "    if graph.get(\"schemaVersion\") != SCHEMA_VERSION:",
  "        errors.append(f\"schemaVersion: expected {SCHEMA_VERSION}\")",
  "    kinds: dict[str, str] = {}",
  "    nodes = graph.get(\"nodes\")",
  "    edges = graph.get(\"edges\")",
  "    if not isinstance(nodes, list) or not isinstance(edges, list):",
  "        return errors + [\"graph: expected lists `nodes` and `edges`\"]",
  "    for i, node in enumerate(nodes):",
  "        where = f\"nodes[{i}]\"",
  "        if not isinstance(node, dict):",
  "            errors.append(f\"{where}: expected an object\")",
  "            continue",
  "        _check_fields(\"NodeAttrs\", node, where, errors)",
  "        node_id = node.get(\"id\")",
  "        if isinstance(node_id, str):",
  "            if node_id in kinds:",
  "                errors.append(f\"{where}: duplicate id {node_id}\")",
  "            kinds[node_id] = str(node.get(\"kind\"))",
  "    for i, edge in enumerate(edges):",
  "        where = f\"edges[{i}]\"",
  "        if not isinstance(edge, dict):",
  "            errors.append(f\"{where}: expected an object\")",
  "            continue",
  "        relation = edge.get(\"relation\")",
  "        if relation not in RELATIONS:",
  "            errors.append(f\"{where}: unknown relation {relation!r}\")",
  "            continue",
  "        assert isinstance(relation, str)",
  "        for end, kind in zip((\"source\", \"target\"), RELATIONS[relation]):",
  "            ref = edge.get(end)",
  "            if ref not in kinds:",
  "                errors.append(f\"{where}.{end}: unknown node {ref!r}\")",
  "            elif kinds[str(ref)] != kind:",
  "                errors.append(f\"{where}.{end}: {ref} is a {kinds[str(ref)]}, {relation} needs a {kind}\")",
  "        if relation in EDGE_ATTRS:",
  "            _check_fields(EDGE_ATTRS[relation], edge, where, errors)",
  "    return errors"]

def pySchema (s : SchemaSpec) : String :=
  let enumLines (e : EnumSpec) :=
    [s!"{e.name} = Literal[{", ".intercalate (e.ctors.map pq)}]"] ++ pyDoc "" e.doc ++ [""]
  let structLines (st : StructSpec) :=
    [s!"class {st.name}(TypedDict):"] ++ pyDoc "    " st.doc ++
    st.fields.flatMap (fun f => [s!"    {f.name}: {pyTy f.ty}"] ++ pyDoc "    " f.doc) ++ ["", ""]
  let edgeLines (a : ArrowSpec) :=
    let bases := match a.attrs with | some t => s!"EdgeBase, {t}" | none => "EdgeBase"
    [s!"class {edgeClass a}({bases}):", s!"    \"\"\"Edge of relation `{a.name}`: {a.source} → {a.target}.\"\"\"", "", ""]
  let fieldTable (st : StructSpec) :=
    [s!"    {pq st.name}: \{"] ++ st.fields.map (fun f => s!"        {pq f.name}: {pySpec f.ty},") ++ ["    },"]
  let lines :=
    [s!"# {headerText "spec/BioMech/Schema.lean"}",
     "\"\"\"Knowledge-graph schema: node and edge types of `graph.json`, and its validator.\"\"\"",
     "", "from __future__ import annotations", "",
     "from typing import Final, Literal, TypedDict, Union", "",
     s!"SCHEMA_VERSION: Final = {s.version}", ""] ++
    s.enums.flatMap enumLines ++
    s.enums.map (fun e => s!"{e.name.toUpper}: Final[tuple[{e.name}, ...]] = ({", ".intercalate (e.ctors.map pq)},)") ++
    ["", ""] ++
    s.structs.flatMap structLines ++
    ["class EdgeBase(TypedDict):", "    \"\"\"Fields every edge carries. `source` and `target` are node ids.\"\"\"",
     "    source: str", "    target: str", "    relation: str", "", ""] ++
    s.arrows.flatMap edgeLines ++
    [s!"Edge = Union[{", ".intercalate (s.arrows.map edgeClass)}]", "", "",
     "class Graph(TypedDict):", "    \"\"\"The shape of `graph.json`.\"\"\"", "    schemaVersion: int",
     "    nodes: list[NodeAttrs]", "    edges: list[Edge]", "", "",
     "# Arrows of the schema quiver: relation -> (source kind, target kind).",
     "RELATIONS: Final[dict[str, tuple[Kind, Kind]]] = {"] ++
    s.arrows.map (fun a => s!"    {pq a.name}: ({pq a.source}, {pq a.target}),") ++ ["}", "",
     "# Relation -> name of its attribute structure in FIELDS.",
     "EDGE_ATTRS: Final[dict[str, str]] = {"] ++
    (s.arrows.filterMap fun a => a.attrs.map fun t => s!"    {pq a.name}: {pq t},") ++ ["}", "",
     "ENUMS: Final[dict[str, tuple[str, ...]]] = {"] ++
    s.enums.map (fun e => s!"    {pq e.name}: {e.name.toUpper},") ++ ["}", "",
     "FieldSpec = Union[str, tuple[str, \"FieldSpec\"]]", "",
     "# Structure -> field -> type spec, read by validate_graph.",
     "FIELDS: Final[dict[str, dict[str, FieldSpec]]] = {"] ++
    s.structs.flatMap fieldTable ++ ["}", "", ""] ++ pyValidator
  "\n".intercalate lines ++ "\n"

end BioMech.Gen
