import BioMech.Gen.Model

/-!
# Import-boundary emitter: `generated/eslint-boundaries.json`

Import rules for `eslint-plugin-boundaries`, from the component digraph of
`BioMech.Components`. The file is shaped as an ESLint flat-config object minus
`files` (which the ESLint config sets), plus two keys starting with `$` that
the consumer drops before use:

```
{
  "$generated": "<header line>",
  "$rootPath": "repository root",          // what element patterns are relative to
  "settings": {
    "boundaries/elements": [               // one element type per component, then shared
      { "type": "GraphStore", "pattern": "web/src/store/**", "mode": "full" },
      { "type": "App", "pattern": "web/src/main.ts", "mode": "full" },
      …,
      { "type": "generated", "pattern": "generated/ts/**", "mode": "full" }
    ],
    "boundaries/ignore": ["**/*.test.ts"]
  },
  "rules": {
    "boundaries/element-types": ["error", {
      "default": "disallow",
      "rules": [                           // one rule per component, in Component.all order
        { "from": ["QueryEngine"], "allow": ["QueryEngine", "GraphStore", "generated"] },
        …
      ]
    }]
  }
}
```

* Element types: a component's directory path `d/` gives the pattern `d/**`; a
  file path gives itself. `mode: "full"` matches the pattern against the whole
  path relative to `boundaries/root-path`, which the consumer sets to the
  repository root.
* Element type `generated` covers `sharedImports`, which every component may
  import.
* `allow` of a component: itself, its targets in `edges` (in edge order), then
  `generated`.
* Files matching `*.test.ts` stay outside the rules (`boundaries/ignore`).
-/

namespace BioMech.Gen

/-- Element type of the shared imports (`sharedImports`). -/
def sharedType : String := "generated"

def boundaryPattern (p : String) : String := if p.endsWith "/" then p ++ "**" else p

def eslintBoundaries (c : ComponentsSpec) : Except String String := do
  if c.components.any (·.name == sharedType) then
    throw s!"eslint-boundaries.json: a component is named {sharedType}, the shared element type"
  let element (ty p : String) : J :=
    .obj [("type", .str ty), ("pattern", .str (boundaryPattern p)), ("mode", .str "full")]
  let elements := c.components.flatMap (fun comp => comp.paths.map (element comp.name)) ++
    c.sharedImports.map (element sharedType)
  let rule (comp : ComponentSpec) : J :=
    let targets := (c.edges.filter (·.1 == comp.name)).map (·.2)
    .obj [("from", J.strs [comp.name]), ("allow", J.strs ([comp.name] ++ targets ++ [sharedType]))]
  let j : J := .obj [
    ("$generated", .str (headerText c.loc.file)),
    ("$rootPath", .str "repository root"),
    ("settings", .obj [
      ("boundaries/elements", .arr elements),
      ("boundaries/ignore", J.strs ["**/*.test.ts"])]),
    ("rules", .obj [
      ("boundaries/element-types", .arr [.str "error", .obj [
        ("default", .str "disallow"),
        ("rules", .arr (c.components.map rule))]])])]
  return j.render ++ "\n"

end BioMech.Gen
