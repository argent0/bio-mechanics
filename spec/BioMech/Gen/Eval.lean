import Lean

/-!
# Evaluation in the compiled specification

The emitters read the specification at run time: `loadEnv` imports the compiled
modules (`.olean` files) into an `Environment`, and `evalTerm` elaborates a Lean
term in that environment and runs it with the Lean interpreter. A term such as
`BioMech.Gait.transitions.map fun t => t.1.ctorIdx` yields plain values
(`Nat`, `String`, lists and pairs of them), which the emitters turn into text.

Enumeration values travel as constructor indices (`ctorIdx`); `ctorNames`
reads the constructor names of the same inductive from the environment, so a
value `i` prints as the `i`-th constructor's name.

## Terms

* *Environment*: the declarations of a set of compiled modules, with their
  docstrings, source ranges, and extension data (notations, attributes).
* *Interpreter*: Lean's evaluator for compiled code stored in `.olean` files; it
  runs the definitions of the specification modules without linking them into
  the `gen` executable.
-/

namespace BioMech.Gen
open Lean Elab Meta

/-- The specification modules the emitters import, in the order the
architecture model lists their theorems. -/
def specModules : List Name :=
  [`BioMech.Schema, `BioMech.GaitFsm, `BioMech.UiFsm, `BioMech.Acyclic,
   `BioMech.Pipeline, `BioMech.Components]

/-- Imports `specModules` with their environment extensions loaded, so that
elaboration, evaluation, and pretty printing work as inside a Lean file. -/
unsafe def loadEnvImpl : IO Environment := do
  initSearchPath (← findSysroot)
  enableInitializersExecution
  importModules (specModules.map ({ module := · })).toArray {} (loadExts := true)

@[implemented_by loadEnvImpl, inherit_doc loadEnvImpl]
opaque loadEnv : IO Environment

/-- Runs a `MetaM` action in `env`. -/
def runMeta {α : Type} (env : Environment) (x : MetaM α) : IO α := do
  let ctx : Core.Context := {
    fileName := "<gen>", fileMap := default, maxHeartbeats := 0,
    options := maxRecDepth.set {} 4096 }
  let (a, _, _) ← x.toIO ctx { env }
  return a

unsafe def evalTermImpl (α : Type) [ToExpr α] [Nonempty α] (src : String) : MetaM α := do
  let stx ← match Parser.runParserCategory (← getEnv) `term src with
    | .ok stx => pure stx
    | .error e => throwError "cannot parse `{src}`: {e}"
  (Term.evalTerm α (toTypeExpr α) stx).run'

/-- Elaborates the Lean term `src` at type `α` and evaluates it. -/
@[implemented_by evalTermImpl]
opaque evalTerm (α : Type) [ToExpr α] [Nonempty α] (src : String) : MetaM α

/-- The last component of `n`, e.g. `idle` for `BioMech.Ui.UiState.idle`. -/
def _root_.Lean.Name.lastName (n : Name) : String :=
  match n with
  | .str _ s => s
  | n => n.toString

/-- Constructor names of the inductive `n`, by index. -/
def ctorNames (n : Name) : MetaM (Array String) := do
  match (← getEnv).find? n with
  | some (.inductInfo v) => return v.ctors.toArray.map (·.lastName)
  | _ => throwError "{n} is missing or is no inductive type"

/-- The constructor of the inductive `ty` at index `i`. -/
def ctorAt (names : Array String) (ty : Name) (i : Nat) : MetaM String :=
  match names[i]? with
  | some s => return s
  | none => throwError "{ty} has no constructor {i}"

/-- Evaluates `src`, a term of type `List ty` for an enumeration `ty`, to the
constructor names of its elements. -/
def evalEnumList (ty : Name) (src : String) : MetaM (List String) := do
  let names ← ctorNames ty
  let idx ← evalTerm (List Nat) s!"(({src}) : List {ty}).map {ty}.ctorIdx"
  idx.mapM (ctorAt names ty)

/-- Evaluates `src`, a term of type `ty`, to its constructor name. -/
def evalEnum (ty : Name) (src : String) : MetaM String := do
  let names ← ctorNames ty
  ctorAt names ty (← evalTerm Nat s!"{ty}.ctorIdx ({src})")

/-- The docstring of `n`, trimmed. -/
def docOf (n : Name) : MetaM (Option String) := do
  return (← findDocString? (← getEnv) n).map (·.trimAscii.toString)

/-- Docstrings of the constructors of `ty`, in constructor order. -/
def ctorDocs (ty : Name) : MetaM (List (String × Option String)) := do
  match (← getEnv).find? ty with
  | some (.inductInfo v) => v.ctors.mapM fun c => return (c.lastName, ← docOf c)
  | _ => throwError "{ty} is missing or is no inductive type"

end BioMech.Gen
