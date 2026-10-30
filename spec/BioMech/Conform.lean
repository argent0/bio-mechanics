import Lean
import BioMech.GaitFsm
import BioMech.UiFsm

/-!
# Trace conformance

`lake exe conform FILE` reads a `trace.json` and checks each recorded trace
against its DFA (contract C5): the gait DFA `Gait.gaitDfa` or the UI DFA
`Ui.uiDfa`. It exits 0 when every trace conforms and 1 otherwise.

## Terms

* *Trace*: what the app records while one DFA runs, a list of steps.
* *Step*: one input event and the state the app holds right after it.
* *Recorded state*: the state a step holds. *Expected state*: the DFA's step
  from the previous recorded state (the start state, for the first step) on
  the step's event.
* *Mismatch*: a step whose recorded state differs from its expected state.
* *Conforms*: a trace conforms when every step's recorded state equals its
  expected state and, for the gait DFA, every recorded state is one of the
  seven phases (`invalid` excluded).
* *Mid-stride*: a gait trace whose last state differs from `loadingResponse`,
  so its word covers a part of a stride at its end. The gait DFA accepts the
  words that cover whole strides.

## The trace format (`trace.json`)

This file is the source of truth for the format; the app's dev-mode recorder
(workstream G) writes it.

```json
{"traces": [
  {"machine": "gait",
   "steps": [{"event": "oppositeToeOff", "state": "midStance"},
             {"event": "heelOff",        "state": "terminalStance"}]},
  {"machine": "ui",
   "steps": [{"event": "play",  "state": "playing"},
             {"event": "pause", "state": "paused"}]}
]}
```

* `machine` is `"gait"` or `"ui"`.
* `event` is a constructor name of `Gait.GaitEvent` or `Ui.UiEvent`; `state` is
  a constructor name of `Gait.GaitPhase` or `Ui.UiState`, the state after the
  event.
* The machine's start state is implied: `loadingResponse` for the gait DFA, so
  a gait recording starts at an initial contact of the reference leg; `idle`
  for the UI DFA.
* Other keys, at every level, are free for the recorder (e.g. a timestamp `t`
  per step) and the checker reads past them.

## Rules

* Every step: the recorded state equals the expected state (`mismatches`).
  This holds for both machines; the UI DFA accepts every word
  (`Ui.accepts_all`), so for `ui` this is the whole check.
* `gait`: every recorded state is one of the seven phases; `invalid` marks an
  event out of order and is an error. A conforming
  trace that ends mid-stride gets a warning; one that ends in `loadingResponse`
  is accepted, it covers whole strides.

Soundness: `evalFrom_of_mismatches_nil` (any DFA), `gait_sound`, `ui_sound`,
and, linking them to the checker's error lists, `gaitConforms_of_gaitErrors`
and `mismatches_nil_of_judge`. A trace whose steps all match records exactly
the states the DFA runs through, so its last recorded state is the DFA's state
after the whole word.
-/

namespace BioMech.Conform
open Lean Elab Term

/-! ## Conformance for any DFA -/

section
variable {α σ : Type} [DecidableEq σ] (M : DFA α σ)

/-- A mismatch: the step's index, its event, the previous recorded state, the
expected state, and the recorded state. -/
structure Mismatch (α σ : Type) where
  step : Nat
  event : α
  previous : σ
  expected : σ
  recorded : σ

/-- The mismatches of a trace `w` that starts in `s`, with step indices from
`k`. Each step is judged from the previous recorded state, so one wrong step
yields one mismatch. -/
def mismatches : σ → List (α × σ) → (k : Nat := 0) → List (Mismatch α σ)
  | _, [], _ => []
  | s, (e, r) :: w, k =>
    if M.step s e = r then mismatches r w (k + 1)
    else ⟨k, e, s, M.step s e, r⟩ :: mismatches r w (k + 1)

/-- The last recorded state of a trace that starts in `s`, and `s` for the
empty trace. -/
def lastState (s : σ) (w : List (α × σ)) : σ := (w.map (·.2)).getLastD s

/-- **Soundness.** A trace whose steps all match ends in the DFA's state after its
whole word: running `M` from `s` on the events gives the last recorded state. -/
theorem evalFrom_of_mismatches_nil :
    ∀ (s : σ) (w : List (α × σ)) (k : Nat), mismatches M s w k = [] →
      M.evalFrom s (w.map (·.1)) = lastState s w
  | _, [], _, _ => rfl
  | s, (e, r) :: w, k, h => by
    unfold mismatches at h
    split at h
    · rename_i hs
      rw [List.map_cons, DFA.evalFrom_cons, hs, evalFrom_of_mismatches_nil r w (k + 1) h]
      simp only [lastState, List.map_cons, List.getLastD_cons]
    · cases h

/-- A trace whose steps all match records, at every step, the DFA's state after
the events up to that step. -/
theorem evalFrom_take_of_mismatches_nil :
    ∀ (s : σ) (w : List (α × σ)) (k : Nat), mismatches M s w k = [] →
      ∀ n, M.evalFrom s ((w.take n).map (·.1)) = lastState s (w.take n)
  | _, [], _, _, n => by simp [lastState]
  | s, (e, r) :: w, k, h, n => by
    cases n with
    | zero => rfl
    | succ n =>
      unfold mismatches at h
      split at h
      · rename_i hs
        rw [List.take_succ_cons, List.map_cons, DFA.evalFrom_cons, hs,
          evalFrom_take_of_mismatches_nil r w (k + 1) h n]
        simp only [lastState, List.map_cons, List.getLastD_cons]
      · cases h

end

/-! ## The gait DFA -/

open Gait in
/-- Index of the first step whose recorded state is `invalid`. -/
def invalidAt (w : List (GaitEvent × GaitPhase)) : Option Nat := w.findIdx? (·.2 == .invalid)

open Gait in
/-- A gait trace conforms: its mismatch list is empty, and `invalidAt` finds
`none`, so every recorded state is one of the seven phases. -/
def gaitConforms (w : List (GaitEvent × GaitPhase)) : Prop :=
  mismatches gaitDfa gaitDfa.start w = [] ∧ invalidAt w = none

open Gait in
/-- **Soundness for the gait DFA.** A conforming gait trace ends in the gait
DFA's state after its whole word; that state differs from `invalid`; and the
word is accepted exactly when the last recorded state is an accept state. -/
theorem gait_sound {w : List (GaitEvent × GaitPhase)} (h : gaitConforms w) :
    gaitDfa.eval (w.map (·.1)) = lastState gaitDfa.start w ∧
      lastState gaitDfa.start w ≠ .invalid ∧
      (w.map (·.1) ∈ gaitDfa.accepts ↔ lastState gaitDfa.start w ∈ gaitDfa.accept) := by
  have he := evalFrom_of_mismatches_nil gaitDfa _ w 0 h.1
  refine ⟨he, ?_, by rw [DFA.mem_accepts, DFA.eval, he]⟩
  have hw : ∀ x ∈ w.map (·.2), x ≠ .invalid := by
    intro x hx
    obtain ⟨p, hp, rfl⟩ := List.mem_map.mp hx
    simpa using List.findIdx?_eq_none_iff.mp h.2 p hp
  unfold lastState
  generalize w.map (·.2) = l at hw
  induction l using List.reverseRecOn with
  | nil => decide
  | append_singleton l x _ => simpa using hw x (by simp)

/-! ## The UI DFA -/

open Ui in
/-- **Soundness for the UI DFA.** A UI trace whose steps all match ends in the UI
DFA's state after its whole word. -/
theorem ui_sound {w : List (UiEvent × UiState)} (h : mismatches uiDfa uiDfa.start w = []) :
    uiDfa.eval (w.map (·.1)) = lastState uiDfa.start w :=
  evalFrom_of_mismatches_nil uiDfa _ w 0 h

/-! ## Names -/

/-- `ctor_table% T`: the list `[("c", T.c), …]` over the constructors of `T`,
in declaration order. -/
elab "ctor_table% " id:ident : term <= expected => do
  let n ← realizeGlobalConstNoOverloadWithInfo id
  let some (.inductInfo v) := (← getEnv).find? n | throwError "{n} needs to be an inductive type"
  let items ← v.ctors.toArray.mapM fun c =>
    `(($(Syntax.mkStrLit c.lastComponentAsString), $(mkCIdent c)))
  elabTerm (← `([$items,*])) expected

/-- Constructor names of `Gait.GaitEvent`. -/
def gaitEvents : List (String × Gait.GaitEvent) := ctor_table% Gait.GaitEvent
/-- Constructor names of `Gait.GaitPhase`. -/
def gaitPhases : List (String × Gait.GaitPhase) := ctor_table% Gait.GaitPhase
/-- Constructor names of `Ui.UiEvent`. -/
def uiEvents : List (String × Ui.UiEvent) := ctor_table% Ui.UiEvent
/-- Constructor names of `Ui.UiState`. -/
def uiStates : List (String × Ui.UiState) := ctor_table% Ui.UiState

/-- The name of a value in a constructor table. -/
def nameIn {β : Type} [BEq β] (table : List (String × β)) (b : β) : String :=
  ((table.find? (·.2 == b)).map (·.1)).getD "?"

/-! ## Reading the JSON -/

/-- One machine's names and its DFA: what the checker needs to read and judge
its traces. -/
structure Machine where
  name : String
  Event : Type
  State : Type
  [decEq : DecidableEq State]
  [beqE : BEq Event]
  events : List (String × Event)
  states : List (String × State)
  dfa : DFA Event State

attribute [instance] Machine.decEq Machine.beqE

/-- The gait DFA as a machine. -/
def gait : Machine := ⟨"gait", _, _, gaitEvents, gaitPhases, Gait.gaitDfa⟩

/-- The UI DFA as a machine. -/
def ui : Machine := ⟨"ui", _, _, uiEvents, uiStates, Ui.uiDfa⟩

/-- Reads the steps of trace `ti` for machine `m`; errors name each unreadable
step. -/
def readSteps (m : Machine) (ti : Nat) (steps : Array Json) :
    Except (Array String) (List (m.Event × m.State)) := Id.run do
  let mut errs := #[]
  let mut out := #[]
  for h : k in [:steps.size] do
    let st := steps[k]
    let at_ := s!"traces[{ti}].steps[{k}]"
    let name (f : String) := (st.getObjValAs? String f).toOption
    match name "event", name "state" with
    | some e, some s =>
      match m.events.lookup e, m.states.lookup s with
      | some e', some s' => out := out.push (e', s')
      | e', s' =>
        if e'.isNone then errs := errs.push s!"{at_}: unknown {m.name} event \"{e}\""
        if s'.isNone then errs := errs.push s!"{at_}: unknown {m.name} state \"{s}\""
    | _, _ => errs := errs.push s!"{at_}: expected an object with string fields `event`, `state`"
  return if errs.isEmpty then .ok out.toList else .error errs

/-- Outcome of one trace: its errors, warnings, and a one-line summary. -/
structure Outcome where
  errors : Array String := #[]
  warnings : Array String := #[]
  summary : String := ""

/-- The error message of a mismatch. -/
def Mismatch.message (m : Machine) (ti : Nat) (x : Mismatch m.Event m.State) : String :=
  s!"traces[{ti}].steps[{x.step}]: {nameIn m.events x.event} from " ++
    s!"{nameIn m.states x.previous}: expected {nameIn m.states x.expected}, " ++
    s!"recorded {nameIn m.states x.recorded}"

/-- Judges one parsed trace of machine `m`. -/
def judge (m : Machine) (ti : Nat) (w : List (m.Event × m.State)) : Outcome :=
  let ms := mismatches m.dfa m.dfa.start w
  { errors := (ms.map (Mismatch.message m ti)).toArray,
    summary := s!"traces[{ti}] {m.name}: {w.length} steps conform" }

/-- A trace whose `judge` errors are empty has an empty mismatch list; for the UI DFA,
`ui_sound` applies to it. -/
theorem mismatches_nil_of_judge {m : Machine} {ti : Nat} {w : List (m.Event × m.State)}
    (h : (judge m ti w).errors = #[]) : mismatches m.dfa m.dfa.start w = [] := by
  have h' := congrArg Array.toList h
  simp only [judge, List.map_eq_nil_iff] at h'
  exact h'

open Gait in
/-- The `invalid` error of a gait trace: the first step whose recorded state is
`invalid`, unless a mismatch at that step already reports it. -/
def invalidErrors (ti : Nat) (w : List (GaitEvent × GaitPhase)) : Array String :=
  match invalidAt w with
  | some k =>
    if (mismatches gaitDfa gaitDfa.start w).any (·.step == k) then #[]
    else
      let previous := if k = 0 then gaitDfa.start else ((w[k - 1]?).map (·.2)).getD .invalid
      #[s!"traces[{ti}].steps[{k}]: {nameIn gaitEvents (((w[k]?).map (·.1)).getD default)} " ++
        s!"from {nameIn gaitPhases previous} leads to invalid: event out of order"]
  | none => #[]

open Gait in
/-- The errors of a parsed gait trace: one per mismatch, then the `invalid`
error. -/
def gaitErrors (ti : Nat) (w : List (GaitEvent × GaitPhase)) : Array String :=
  (judge gait ti w).errors ++ invalidErrors ti w

open Gait in
/-- **The checker's verdict is sound.** A gait trace with an empty error list conforms,
so `gait_sound` applies to it. -/
theorem gaitConforms_of_gaitErrors {ti : Nat} {w : List (GaitEvent × GaitPhase)}
    (h : gaitErrors ti w = #[]) : gaitConforms w := by
  simp only [gaitErrors, Array.append_eq_empty_iff] at h
  obtain ⟨hm, hi⟩ := h
  have hm : mismatches gaitDfa gaitDfa.start w = [] := mismatches_nil_of_judge hm
  refine ⟨hm, ?_⟩
  unfold invalidErrors at hi
  split at hi
  · simp [hm] at hi
  · assumption

open Gait in
/-- Judges one parsed gait trace: `gaitErrors`, then whole strides. -/
def judgeGait (ti : Nat) (w : List (GaitEvent × GaitPhase)) : Outcome :=
  let base := judge gait ti w
  let errors := gaitErrors ti w
  let last := lastState gaitDfa.start w
  if !errors.isEmpty then { base with errors }
  else if last ∈ acceptStates then
    { base with errors, summary := base.summary ++ ", accepted (whole strides)" }
  else
    { base with
      errors,
      warnings := #[s!"traces[{ti}] gait: warning: stops mid-stride in " ++
        s!"{nameIn gaitPhases last}; accepted words end in loadingResponse"],
      summary := base.summary ++ ", mid-stride" }

/-- The errors `judgeGait` reports are `gaitErrors`. -/
theorem judgeGait_errors (ti : Nat) (w : List (Gait.GaitEvent × Gait.GaitPhase)) :
    (judgeGait ti w).errors = gaitErrors ti w := by
  unfold judgeGait; dsimp only; split <;> (try split) <;> rfl

/-- Checks one trace object at index `ti`. -/
def checkTrace (ti : Nat) (t : Json) : Outcome :=
  let steps := ((t.getObjVal? "steps").toOption.bind (·.getArr?.toOption))
  match (t.getObjValAs? String "machine").toOption, steps with
  | some "gait", some st =>
    match readSteps gait ti st with
    | .ok w => judgeGait ti w
    | .error es => { errors := es }
  | some "ui", some st =>
    match readSteps ui ti st with
    | .ok w => judge ui ti w
    | .error es => { errors := es }
  | some other, some _ => { errors := #[s!"traces[{ti}]: unknown machine \"{other}\", expected gait or ui"] }
  | _, _ => { errors := #[s!"traces[{ti}]: expected string `machine` and array `steps`"] }

end BioMech.Conform

open BioMech.Conform in
/-- `lake exe conform FILE`: exit 0 when every trace conforms, 1 otherwise, 2 on
a usage error. -/
def main (args : List String) : IO UInt32 := do
  let [path] := args | IO.eprintln "usage: lake exe conform FILE"; return 2
  let text ← try IO.FS.readFile path catch e => IO.eprintln s!"{path}: {e}"; return 1
  match Lean.Json.parse text with
  | .error e => IO.println s!"{path}: invalid JSON: {e}"; return 1
  | .ok j =>
    let some traces := (j.getObjVal? "traces").toOption.bind (·.getArr?.toOption)
      | IO.println s!"{path}: expected an object with an array `traces`"; return 1
    let mut nErr := 0
    for h : ti in [:traces.size] do
      let o := checkTrace ti traces[ti]
      for l in o.errors do IO.println l
      for l in o.warnings do IO.println l
      if o.errors.isEmpty then IO.println o.summary
      nErr := nErr + o.errors.size
    if nErr == 0 then
      IO.println s!"{path}: {traces.size} trace(s) conform"
      return 0
    else
      IO.println s!"{path}: {nErr} error(s)"
      return 1
