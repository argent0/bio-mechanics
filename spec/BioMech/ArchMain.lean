import BioMech.Arch.Owner
import BioMech.Arch.Print

/-!
# `lake exe arch`

* `arch check [--root DIR]` — every file from `git ls-files --cached --others
  --exclude-standard` has exactly one owner; exits 1 and lists offenders otherwise.
* `arch export [--root DIR]` — writes `generated/modules.json`.
* `arch print [--detail N]` — prints the map, `N` in 0–3 (default 1).

`--root` defaults to `..`, the repository root seen from `spec/`.
-/

open BioMech.Arch

def argValue (args : List String) (flag : String) : Option String :=
  match args.dropWhile (· != flag) with
  | _ :: v :: _ => some v
  | _ => none

def trackedFiles (root : String) : IO (List String) := do
  let out ← IO.Process.output
    { cmd := "git", args := #["ls-files", "--cached", "--others", "--exclude-standard"], cwd := root }
  if out.exitCode != 0 then throw <| IO.userError s!"git ls-files failed: {out.stderr}"
  return (out.stdout.splitOn "\n").filter (· ≠ "")

def check (root : String) : IO UInt32 := do
  let files ← trackedFiles root
  let errs := files.filterMap fun f => match owner f with | .error e => some e | .ok _ => none
  for e in errs do IO.eprintln e
  if errs.isEmpty then
    IO.println s!"arch check: {files.length} files, each with exactly one owner"
    return 0
  return 1

def main (args : List String) : IO UInt32 := do
  let root := (argValue args "--root").getD ".."
  match args with
  | "check" :: _ => check root
  | "export" :: _ =>
    let path := System.FilePath.mk root / "generated" / "modules.json"
    IO.FS.createDirAll (System.FilePath.mk root / "generated")
    IO.FS.writeFile path (modulesJson.pretty ++ "\n")
    IO.println s!"wrote {path}"
    return 0
  | "print" :: _ =>
    let detail := ((argValue args "--detail").bind String.toNat?).getD 1
    IO.print (render (min detail 3))
    return 0
  | _ =>
    IO.eprintln "usage: arch (check | export | print [--detail 0..3]) [--root DIR]"
    return 2
