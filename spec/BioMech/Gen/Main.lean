import BioMech.Gen.Ts
import BioMech.Gen.Py

/-!
# `lake exe gen [--root DIR]`

Writes every generated file under `DIR/generated/` (default `..`, the
repository root seen from `spec/`). Output is deterministic, so a regenerate on
a clean tree gives an empty `git diff`.
-/

open BioMech.Gen

def outputs (s : SchemaSpec) : List (String × String) :=
  [("generated/ts/types.ts", tsTypes s),
   ("generated/py/schema.py", pySchema s)]

def main (args : List String) : IO UInt32 := do
  let root := match args.dropWhile (· != "--root") with
    | _ :: v :: _ => v
    | _ => ".."
  let schema ← loadSchema
  for (rel, text) in outputs schema do
    let path := System.FilePath.mk root / rel
    if let some dir := path.parent then IO.FS.createDirAll dir
    IO.FS.writeFile path text
    IO.println s!"wrote {rel}"
  return 0
