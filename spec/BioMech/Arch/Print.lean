import BioMech.Arch.Export

/-!
# Text drawing of the module map

`print --detail N` draws one row per layer, generators on top.
* 0 — module ids per layer, then one line per API: `C1 ─ coordinator → A, B`.
* 1 — a box per module with its name and the APIs it produces and consumes.
* 2 — adds a head line per box: language · model · state.
* 3 — adds owned paths and acceptance commands, and API files below the map.
-/

namespace BioMech.Arch

def pad (s : String) (w : Nat) : String := s ++ "".pushn ' ' (w - s.length)

def apiNames (as : List Api) : String :=
  if as.isEmpty then "—" else ", ".intercalate (as.map (·.id.name))

/-- Lines of one module's box. -/
def box (detail : Nat) (m : Module) : List String :=
  let body :=
    [s!"{m.id.name}  {m.name}"] ++
    (if detail ≥ 2 then [s!"{m.lang} · {m.model} · {m.state.name}"] else []) ++
    [s!"out: {apiNames (produces m.id)}", s!"in:  {apiNames (consumes m.id)}"] ++
    (if detail ≥ 3 then m.paths.map ("• " ++ ·) ++ m.acceptance.map ("$ " ++ ·) else [])
  let w := (body.map (·.length)).foldl max 0
  [s!"┌{"".pushn '─' (w + 2)}┐"] ++ body.map (fun l => s!"│ {pad l w} │") ++
    [s!"└{"".pushn '─' (w + 2)}┘"]

/-- Places boxes side by side, padding shorter boxes with blank lines. -/
def besides (boxes : List (List String)) : List String :=
  let h := (boxes.map (·.length)).foldl max 0
  let w (b : List String) := (b.map (·.length)).foldl max 0
  let filled := boxes.map fun b => b ++ List.replicate (h - b.length) (pad "" (w b))
  (List.range h).map fun i => "  ".intercalate (filled.map fun b => pad (b.getD i "") (w b))

def layers : List (List Module) :=
  let depth := (modules.map (layer ·.id)).foldl max 0
  (List.range (depth + 1)).map fun d => modules.filter (layer ·.id == d)

def apiLine (detail : Nat) (a : Api) : String :=
  let base := s!"{a.id.name} {a.name} ─ {a.producer.name} → {", ".intercalate (a.consumers.map (·.name))}"
  if detail ≥ 3 then base ++ s!"   [{", ".intercalate a.files}]" else base

def render (detail : Nat) : String :=
  let rows := layers.map fun ms =>
    if detail == 0 then ["  ".intercalate (ms.map (·.id.name))]
    else besides (ms.map (box detail))
  let sep := if detail == 0 then [] else [""]
  let mapLines := rows.foldl (fun acc r => acc ++ (if acc.isEmpty then [] else sep ++ ["  ↓"] ++ sep) ++ r) []
  "\n".intercalate (mapLines ++ ["", "APIs:"] ++ apis.map (apiLine detail)) ++ "\n"

end BioMech.Arch
