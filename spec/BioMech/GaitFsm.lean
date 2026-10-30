import Mathlib.Computability.DFA

/-!
# Gait cycle DFA

## Terms

* *DFA* (deterministic finite automaton): finite states, a start state, a set of
  accept states, and a total `step` function from a state and an input symbol
  to the next state. Mathlib's `DFA α σ` has alphabet `α` and states `σ`.
* *Word*: a finite list of input symbols, read left to right; here gait events
  in time order.
* *Reference leg*: the leg the automaton follows. *Opposite* names the other leg.
* *Gait event*: an instant of the gait cycle, e.g. the foot touching the ground.
* *Gait phase*: the interval between two consecutive gait events.
* *Stride*: one full gait cycle of the reference leg, from one initial contact
  to the next.
* *Sink state*: a state that every event maps back to itself. *Absorbing*: once
  the automaton enters it, every word keeps it there.

## The automaton

The gait DFA follows the reference leg through the seven phases of the gait
cycle, in the standard phase division (Perry): four stance phases (foot on the
ground) and three swing phases (foot in the air). Each phase ends at exactly
one gait event, and that event opens the next phase (`one_event_per_phase`).
An event that arrives out of order moves the automaton to the sink state
`invalid`, which keeps `step` total (`step_eq_invalid_of_not_mem`).

Decision D-001: initial contact is an instant, carried by the event
`initialContact`, which moves the automaton from terminal swing to loading
response.

**Start and accept.** The automaton starts in `loadingResponse`, the phase that
opens at the instant of initial contact, so a recording starts at an initial
contact of the reference leg and the word holds the events that follow it. The
accept states are `{loadingResponse}`: a word is accepted when it ends right
after an initial contact, so it covers whole strides. `strideWord` is one stride
(`strideWord_accepted`), and every repetition of it is accepted
(`strides_accepted`).

**Emitter data** (read by `lake exe gen`): `GaitPhase.phases`, `GaitPhase.all`,
`GaitEvent.all`, `transitions`, `gaitDfa.start`, `acceptStates`, `strideWord`.
`transitions` is the single source of `step`, so the generated tables and the
automaton the theorems speak about are one and the same.
-/

namespace BioMech.Gait

/-! ## States and events -/

/-- States of the gait DFA: the seven gait phases of the reference leg, in
stride order, plus the sink state `invalid`. The percentages are typical
boundaries in percent of the stride (Perry); the pipeline measures the actual
ones per trial (`HasPhaseAttrs`). -/
inductive GaitPhase
  /-- Stance, about 0–10 %: the leg takes the body's weight. From initial contact
  to opposite toe-off. -/
  | loadingResponse
  /-- Stance, about 10–30 %: the body passes over the supporting foot. From
  opposite toe-off to heel-off. -/
  | midStance
  /-- Stance, about 30–50 %: the heel rises and the body moves ahead of the foot.
  From heel-off to opposite initial contact. -/
  | terminalStance
  /-- Stance, about 50–60 %: both feet are on the ground and the weight shifts to
  the opposite leg. From opposite initial contact to toe-off. -/
  | preSwing
  /-- Swing, about 60–73 %: the foot lifts and the thigh moves forward. From
  toe-off to feet adjacent. -/
  | initialSwing
  /-- Swing, about 73–87 %: the swinging leg passes the supporting leg. From feet
  adjacent to tibia vertical. -/
  | midSwing
  /-- Swing, about 87–100 %: the leg reaches forward for the next contact. From
  tibia vertical to initial contact. -/
  | terminalSwing
  /-- Sink state: an event out of order leads here, and every event keeps the
  automaton here. -/
  | invalid
  deriving DecidableEq, Repr, Inhabited

/-- Input symbols of the gait DFA: the gait events that bound the phases, named
from the reference leg. -/
inductive GaitEvent
  /-- The reference foot touches the ground (an instant, decision D-001). Ends
  terminal swing and opens loading response. -/
  | initialContact
  /-- The opposite foot leaves the ground. Ends loading response. -/
  | oppositeToeOff
  /-- The reference heel rises from the ground. Ends mid-stance. -/
  | heelOff
  /-- The opposite foot touches the ground. Ends terminal stance. -/
  | oppositeInitialContact
  /-- The reference foot leaves the ground. Ends pre-swing. -/
  | toeOff
  /-- The swinging foot passes the supporting foot. Ends initial swing. -/
  | feetAdjacent
  /-- The tibia of the swinging leg reaches vertical. Ends mid-swing. -/
  | tibiaVertical
  deriving DecidableEq, Repr, Inhabited

/-- The seven gait phases in stride order, from loading response to terminal
swing: the phase bands of the timeline. -/
def GaitPhase.phases : List GaitPhase :=
  [.loadingResponse, .midStance, .terminalStance, .preSwing,
   .initialSwing, .midSwing, .terminalSwing]

/-- Every state: the seven phases in stride order, then `invalid`. -/
def GaitPhase.all : List GaitPhase := GaitPhase.phases ++ [.invalid]

/-- Every event, in phase order: the event at each position opens the phase at
the same position of `GaitPhase.phases` (`event_opens_phase`). -/
def GaitEvent.all : List GaitEvent :=
  [.initialContact, .oppositeToeOff, .heelOff, .oppositeInitialContact,
   .toeOff, .feetAdjacent, .tibiaVertical]

/-- `GaitPhase.all` lists every state. -/
theorem GaitPhase.mem_all (p : GaitPhase) : p ∈ GaitPhase.all := by cases p <;> decide

/-- `GaitPhase.all` lists each state once. -/
theorem GaitPhase.all_nodup : GaitPhase.all.Nodup := by decide

/-- `GaitPhase.phases` holds exactly the states other than `invalid`. -/
theorem GaitPhase.mem_phases (p : GaitPhase) : p ∈ GaitPhase.phases ↔ p ≠ .invalid := by
  cases p <;> decide

/-- `GaitEvent.all` lists every event. -/
theorem GaitEvent.mem_all (e : GaitEvent) : e ∈ GaitEvent.all := by cases e <;> decide

/-- `GaitEvent.all` lists each event once. -/
theorem GaitEvent.all_nodup : GaitEvent.all.Nodup := by decide

/-- The states form a finite type, enumerated by `GaitPhase.all`. -/
instance : Fintype GaitPhase := ⟨⟨GaitPhase.all, GaitPhase.all_nodup⟩, GaitPhase.mem_all⟩

/-- The events form a finite type, enumerated by `GaitEvent.all`. -/
instance : Fintype GaitEvent := ⟨⟨GaitEvent.all, GaitEvent.all_nodup⟩, GaitEvent.mem_all⟩

/-! ## Transitions -/

/-- The transition table, one `(from, event, to)` row per phase boundary, in
stride order from the start state. It is the single source of `step`; every
(phase, event) pair absent from it goes to `invalid`. -/
def transitions : List (GaitPhase × GaitEvent × GaitPhase) :=
  [(.loadingResponse, .oppositeToeOff,         .midStance),
   (.midStance,       .heelOff,                .terminalStance),
   (.terminalStance,  .oppositeInitialContact, .preSwing),
   (.preSwing,        .toeOff,                 .initialSwing),
   (.initialSwing,    .feetAdjacent,           .midSwing),
   (.midSwing,        .tibiaVertical,          .terminalSwing),
   (.terminalSwing,   .initialContact,         .loadingResponse)]

/-- One step of the gait DFA: the target of the row of `transitions` for
`(s, e)`, and `invalid` for every pair absent from the table. -/
def step (s : GaitPhase) (e : GaitEvent) : GaitPhase :=
  match transitions.find? (fun t => t.1 == s && t.2.1 == e) with
  | some t => t.2.2
  | none => .invalid

/-- The accept states: `loadingResponse` alone, so accepted words cover whole
strides. -/
def acceptStates : List GaitPhase := [.loadingResponse]

/-- The gait DFA: `step` from `transitions`, start `loadingResponse` (the phase
that opens at initial contact), accept states `acceptStates`. -/
def gaitDfa : DFA GaitEvent GaitPhase where
  step := step
  start := .loadingResponse
  accept := {s | s ∈ acceptStates}

/-- Membership in the accept states is decidable, by lookup in `acceptStates`. -/
instance : DecidablePred (· ∈ gaitDfa.accept) :=
  fun s => inferInstanceAs (Decidable (s ∈ acceptStates))

/-- Acceptance of a word is decidable and computable: run the automaton, then
look up the final state. -/
instance : DecidablePred (· ∈ gaitDfa.accepts) :=
  fun _ => decidable_of_iff _ gaitDfa.mem_accepts.symm

/-! ## The table and `step` agree

Some proofs use `decide +kernel`: the kernel evaluates the decision procedure
directly, where the elaborator's evaluator reaches its recursion limit on the
table. -/

/-- Every row of `transitions` is a step of the gait DFA. -/
theorem step_of_mem : ∀ t ∈ transitions, gaitDfa.step t.1 t.2.1 = t.2.2 := by decide +kernel

/-- Every (phase, event) pair absent from `transitions` goes to `invalid`. -/
theorem step_eq_invalid_of_not_mem :
    ∀ s e, (s, e) ∉ transitions.map (fun t => (t.1, t.2.1)) → gaitDfa.step s e = .invalid := by
  decide

/-- Each (phase, event) pair heads at most one row, so the table is a function
and emitters may key it by `(from, event)`. -/
theorem transitions_keys_nodup : (transitions.map (fun t => (t.1, t.2.1))).Nodup := by decide

/-- Every row starts and ends in one of the seven phases; `invalid` appears only
as the default target. -/
theorem transitions_phases :
    ∀ t ∈ transitions, t.1 ∈ GaitPhase.phases ∧ t.2.2 ∈ GaitPhase.phases := by decide +kernel

/-- Each of the seven phases ends at exactly one event: the gait cycle is a
single loop through the phases. -/
theorem one_event_per_phase :
    ∀ s ∈ GaitPhase.phases, (transitions.filter (·.1 == s)).length = 1 := by decide

/-- `GaitEvent.all` and `GaitPhase.phases` run side by side: the event at each
position opens the phase at the same position. -/
theorem event_opens_phase :
    ∀ ep ∈ GaitEvent.all.zip GaitPhase.phases, ∃ s, (s, ep.1, ep.2) ∈ transitions := by
  decide

/-! ## One stride -/

/-- One stride from the start state: the seven events in order, from opposite
toe-off to the next initial contact. -/
def strideWord : List GaitEvent :=
  [.oppositeToeOff, .heelOff, .oppositeInitialContact, .toeOff,
   .feetAdjacent, .tibiaVertical, .initialContact]

/-- One stride takes the start state back to the start state. -/
theorem strideWord_returns : gaitDfa.eval strideWord = gaitDfa.start := rfl

/-- One stride is accepted. -/
theorem strideWord_accepted : strideWord ∈ gaitDfa.accepts := by decide

open scoped Computability in
/-- Every whole number of strides (the Kleene star of `strideWord`, zero strides
included) is accepted. -/
theorem strides_accepted : ∀ w ∈ ({strideWord} : Language GaitEvent)∗, w ∈ gaitDfa.accepts :=
  fun _ hw => by
    rw [DFA.mem_accepts, DFA.eval, DFA.evalFrom_of_pow gaitDfa strideWord_returns hw]
    decide

/-- The states along `strideWord`, after each of its first seven prefixes, are
the seven phases in stride order. -/
theorem stride_trace :
    (List.range strideWord.length).map (fun n => gaitDfa.eval (strideWord.take n)) =
      GaitPhase.phases := rfl

/-- Every one of the seven phases is the state after some prefix of `strideWord`. -/
theorem every_phase_visited :
    ∀ p ∈ GaitPhase.phases, ∃ n < strideWord.length, gaitDfa.eval (strideWord.take n) = p := by
  decide

/-! ## Events out of order -/

/-- Every event keeps `invalid` in `invalid`. -/
theorem step_invalid (e : GaitEvent) : gaitDfa.step .invalid e = .invalid := by
  cases e <;> rfl

/-- `invalid` is absorbing: every word keeps the automaton in `invalid`. -/
theorem evalFrom_invalid (w : List GaitEvent) : gaitDfa.evalFrom .invalid w = .invalid := by
  induction w with
  | nil => rfl
  | cons e w ih => rw [DFA.evalFrom_cons, step_invalid, ih]

/-- Once a prefix lands in `invalid`, every extension of it is rejected. -/
theorem rejects_of_eval_invalid {u : List GaitEvent} (h : gaitDfa.eval u = .invalid)
    (v : List GaitEvent) : u ++ v ∉ gaitDfa.accepts := by
  rw [DFA.mem_accepts, DFA.eval, DFA.evalFrom_of_append, ← DFA.eval, h, evalFrom_invalid]
  decide

/-- Example: opposite initial contact right after opposite toe-off skips heel-off,
so the automaton lands in `invalid`. -/
theorem skipped_heelOff : gaitDfa.eval [.oppositeToeOff, .oppositeInitialContact] = .invalid :=
  rfl

/-- Example: every word that starts by skipping heel-off is rejected. -/
theorem skipped_heelOff_rejected (v : List GaitEvent) :
    [.oppositeToeOff, .oppositeInitialContact] ++ v ∉ gaitDfa.accepts :=
  rejects_of_eval_invalid skipped_heelOff v

end BioMech.Gait
