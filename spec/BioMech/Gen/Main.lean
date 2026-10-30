import BioMech.Gen.Ts
import BioMech.Gen.Py
import BioMech.Gen.Build
import BioMech.Gen.Boundaries
import BioMech.Gen.Diagrams

/-!
# `lake exe gen [--root DIR]`

Writes every generated file under `DIR/generated/` (default `..`, the
repository root seen from `spec/`). Output is deterministic, so a regenerate on
a clean tree gives an empty `git diff`.

The emitters read the compiled specification modules (`specModules`) at run
time, through `loadEnv`:

| File | Emitter |
|---|---|
| `generated/ts/types.ts`, `generated/py/schema.py` | `tsTypes`, `pySchema` |
| `generated/ts/gaitFsm.ts`, `generated/ts/uiFsm.ts`, `generated/py/gait_fsm.py` | `tsFsm`, `pyFsm` |
| `generated/pipeline.ninja`, `generated/py/pipeline_paths.py` | `ninjaFile`, `pipelinePaths` |
| `generated/eslint-boundaries.json` | `eslintBoundaries` |
| `generated/architecture.json` | `architectureJson` |
| `generated/diagrams/*.mmd`, `*.dot` | `diagrams` |

`generated/modules.json` comes from `lake exe arch export`.

## Interpreted run

Loading the environment extensions and evaluating Lean terms run the Lean
interpreter, which calls into the native code of `Init`, `Std`, and `Lean`. The
`gen` executable exports those symbols once its `lean_exe` sets
`supportInterpreter := true`; until then, `main` re-runs this file with
`lean --run`, where the interpreter finds them, and passes on the exit code.
`interpretedVar` marks the inner run.
-/

open BioMech.Gen

def outputs (env : Lean.Environment) : IO (List (String × String)) := do
  let s ← loadSchema env
  let (kinds, kindLoc) ← schemaKinds env
  let m ← loadModel env
  let paths ← IO.ofExcept (pipelinePaths m.pipeline)
  let boundaries ← IO.ofExcept (eslintBoundaries m.components)
  return [("generated/ts/types.ts", tsTypes s),
    ("generated/py/schema.py", pySchema s),
    ("generated/ts/gaitFsm.ts", tsFsm m.gait),
    ("generated/ts/uiFsm.ts", tsFsm m.ui),
    ("generated/py/gait_fsm.py", pyFsm m.gait),
    ("generated/pipeline.ninja", ninjaFile m.pipeline),
    ("generated/py/pipeline_paths.py", paths),
    ("generated/eslint-boundaries.json", boundaries),
    ("generated/architecture.json", architectureJson s kinds kindLoc m)] ++
    diagrams s kinds kindLoc m

/-- Set in the environment of the interpreted run. -/
def interpretedVar : String := "BIOMECH_GEN_INTERPRETED"

/-- `args` with a relative `--root` value resolved against the current
directory, since the interpreted run starts in `spec/`. -/
def absoluteRoot (args : List String) : IO (List String) := do
  let cwd ← IO.currentDir
  let rec go : List String → List String
    | "--root" :: v :: rest =>
      let p := System.FilePath.mk v
      "--root" :: (if p.isAbsolute then v else (cwd / p).toString) :: go rest
    | a :: rest => a :: go rest
    | [] => []
  return go args

/-- Runs this file under `lean --run` with `args`; returns its exit code. The
executable sits at `spec/.lake/build/bin/gen`, so the source sits four levels
up, at `spec/BioMech/Gen/Main.lean`. The interpreted run starts in `spec/`, so
the default root `..` is the repository root wherever `gen` starts. -/
def runInterpreted (args : List String) : IO UInt32 := do
  let args ← absoluteRoot args
  let app ← IO.appPath
  let some spec := app.parent.bind (·.parent) |>.bind (·.parent) |>.bind (·.parent)
    | throw <| IO.userError s!"cannot locate spec/ from {app}"
  let lean := (← Lean.findSysroot) / "bin" / "lean"
  let child ← IO.Process.spawn {
    cmd := lean.toString, cwd := spec,
    args := #["--run", "BioMech/Gen/Main.lean"] ++ args.toArray,
    env := #[(interpretedVar, some "1")] }
  return (← child.wait)

def main (args : List String) : IO UInt32 := do
  if (← IO.getEnv interpretedVar).isNone then return ← runInterpreted args
  let root := match args.dropWhile (· != "--root") with
    | _ :: v :: _ => v
    | _ => ".."
  let env ← loadEnv
  for (rel, text) in ← outputs env do
    let path := System.FilePath.mk root / rel
    if let some dir := path.parent then IO.FS.createDirAll dir
    IO.FS.writeFile path text
    IO.println s!"wrote {rel}"
  return 0
