import Mathlib.Computability.DFA

/-!
# UI DFA

## Terms

* *DFA* (deterministic finite automaton): finite states, a start state, a set of
  accept states, and a total `step` function from a state and an input symbol
  to the next state. Mathlib's `DFA α σ` has alphabet `α` and states `σ`.
* *Word*: a finite list of input symbols, read left to right; here user input
  events in time order.
* *Timeline*: the bar under the 3D view that shows the movement cycle with its
  phase bands. *Playhead*: the marker on the timeline at the frame on screen.
* *Scrubbing*: dragging the playhead along the timeline with the pointer held.
* *Inspector*: the panel that shows one selected graph node (a muscle, joint,
  bone, …) at the frame on screen.
* *Self-loop*: a step that leaves the state as it is. An *ignored event* is an
  event whose step in the current state is a self-loop.
* *Reset word*: one word that takes every state to the same state; here
  `resetWord` takes every state to `idle`.

## The automaton

The UI DFA is the state of the movement player: a timeline player with
scrubbing and a node inspector. The app holds one `UiState`, feeds every user
input event to `step`, and renders the state it gets back.

**Ignored events self-loop.** A (state, event) pair absent from `transitions`
leaves the state as it is (`step_of_not_mem`): the event is ignored in that
state, e.g. `pause` while `idle`. The app may grey out the controls of ignored
events. Self-loops keep `step` total with the five player states alone, and
every state can return to `idle` (`reaches_idle`); a sink state, in contrast,
would trap the player.

**Start and accept.** The automaton starts in `idle`. Every state is an accept
state, so every word is accepted (`accepts_all`): every sequence of user input
is a legal session. The content of the UI DFA is its state sequence, which the
app renders and the trace checker compares against the recorded states.

**Emitter data** (read by `lake exe gen`): `UiState.all`, `UiEvent.all`,
`transitions`, `uiDfa.start`, `acceptStates`, `resetWord`. `transitions` is the
single source of `step`, so the generated table and the automaton the theorems
speak about are one and the same.
-/

namespace BioMech.Ui

/-! ## States and events -/

/-- States of the movement player. -/
inductive UiState
  /-- The playhead rests at the start of the cycle and the inspector is closed. -/
  | idle
  /-- The animation runs and the playhead advances. -/
  | playing
  /-- The animation holds still at the playhead's frame. -/
  | paused
  /-- The user drags the playhead; the frame on screen follows the pointer. -/
  | scrubbing
  /-- The inspector is open on a selected node; the animation holds still at
  the playhead's frame. -/
  | inspectingNode
  deriving DecidableEq, Repr, Inhabited

/-- User input events of the movement player. -/
inductive UiEvent
  /-- The user presses play. -/
  | play
  /-- The user presses pause. -/
  | pause
  /-- The user presses stop: the playhead returns to the start. -/
  | stop
  /-- The user grabs the playhead. -/
  | scrubStart
  /-- The user releases the playhead. -/
  | scrubEnd
  /-- The user clicks a node, in the 3D view or the graph view. -/
  | selectNode
  /-- The user closes the inspector. -/
  | closeInspector
  /-- The playhead reaches the end of the recording (sent by the player). -/
  | reachEnd
  deriving DecidableEq, Repr, Inhabited

/-- Every state, in constructor order. -/
def UiState.all : List UiState := [.idle, .playing, .paused, .scrubbing, .inspectingNode]

/-- Every event, in constructor order. -/
def UiEvent.all : List UiEvent :=
  [.play, .pause, .stop, .scrubStart, .scrubEnd, .selectNode, .closeInspector, .reachEnd]

/-- `UiState.all` lists every state. -/
theorem UiState.mem_all (s : UiState) : s ∈ UiState.all := by cases s <;> decide

/-- `UiState.all` lists each state once. -/
theorem UiState.all_nodup : UiState.all.Nodup := by decide

/-- `UiEvent.all` lists every event. -/
theorem UiEvent.mem_all (e : UiEvent) : e ∈ UiEvent.all := by cases e <;> decide

/-- `UiEvent.all` lists each event once. -/
theorem UiEvent.all_nodup : UiEvent.all.Nodup := by decide

/-- The states form a finite type, enumerated by `UiState.all`. -/
instance : Fintype UiState := ⟨⟨UiState.all, UiState.all_nodup⟩, UiState.mem_all⟩

/-- The events form a finite type, enumerated by `UiEvent.all`. -/
instance : Fintype UiEvent := ⟨⟨UiEvent.all, UiEvent.all_nodup⟩, UiEvent.mem_all⟩

/-! ## Transitions -/

/-- The transition table: one `(from, event, to)` row per event with a meaning
in its state, grouped by source state. It is the single source of `step`; every
(state, event) pair absent from it is an ignored event and self-loops.

* `idle`: play starts the animation; grabbing the playhead scrubs; a click opens
  the inspector.
* `playing`: pause and the end of the recording hold the frame; stop rewinds;
  grabbing the playhead or clicking a node holds the animation first.
* `paused`: play resumes; stop rewinds; grab and click as from `idle`.
* `scrubbing`: releasing the playhead pauses at the chosen frame; every other
  event is ignored while the pointer is held.
* `inspectingNode`: a click on another node keeps the inspector open on it;
  closing the inspector leaves the animation paused; play, stop, and grab act
  as from `paused` and close the inspector. -/
def transitions : List (UiState × UiEvent × UiState) :=
  [(.idle,           .play,           .playing),
   (.idle,           .scrubStart,     .scrubbing),
   (.idle,           .selectNode,     .inspectingNode),
   (.playing,        .pause,          .paused),
   (.playing,        .stop,           .idle),
   (.playing,        .reachEnd,       .paused),
   (.playing,        .scrubStart,     .scrubbing),
   (.playing,        .selectNode,     .inspectingNode),
   (.paused,         .play,           .playing),
   (.paused,         .stop,           .idle),
   (.paused,         .scrubStart,     .scrubbing),
   (.paused,         .selectNode,     .inspectingNode),
   (.scrubbing,      .scrubEnd,       .paused),
   (.inspectingNode, .play,           .playing),
   (.inspectingNode, .stop,           .idle),
   (.inspectingNode, .scrubStart,     .scrubbing),
   (.inspectingNode, .selectNode,     .inspectingNode),
   (.inspectingNode, .closeInspector, .paused)]

/-- One step of the UI DFA: the target of the row of `transitions` for `(s, e)`,
and `s` itself for every pair absent from the table. -/
def step (s : UiState) (e : UiEvent) : UiState :=
  match transitions.find? (fun t => t.1 == s && t.2.1 == e) with
  | some t => t.2.2
  | none => s

/-- The accept states: every state, so every word is accepted. -/
def acceptStates : List UiState := UiState.all

/-- The UI DFA: `step` from `transitions`, start `idle`, accept states
`acceptStates`. -/
def uiDfa : DFA UiEvent UiState where
  step := step
  start := .idle
  accept := {s | s ∈ acceptStates}

/-- Membership in the accept states is decidable, by lookup in `acceptStates`. -/
instance : DecidablePred (· ∈ uiDfa.accept) :=
  fun s => inferInstanceAs (Decidable (s ∈ acceptStates))

/-- Acceptance of a word is decidable and computable: run the automaton, then
look up the final state. -/
instance : DecidablePred (· ∈ uiDfa.accepts) :=
  fun _ => decidable_of_iff _ uiDfa.mem_accepts.symm

/-- Every word is accepted: every sequence of user input is a legal session. -/
theorem accepts_all (w : List UiEvent) : w ∈ uiDfa.accepts := UiState.mem_all _

/-! ## The table and `step` agree

These proofs use `decide +kernel`: the kernel evaluates the decision procedure
directly, where the elaborator's evaluator reaches its recursion limit on the
table. -/

/-- Every row of `transitions` is a step of the UI DFA. -/
theorem step_of_mem : ∀ t ∈ transitions, uiDfa.step t.1 t.2.1 = t.2.2 := by decide +kernel

/-- Every (state, event) pair absent from `transitions` self-loops. -/
theorem step_of_not_mem :
    ∀ s e, (s, e) ∉ transitions.map (fun t => (t.1, t.2.1)) → uiDfa.step s e = s := by
  decide +kernel

/-- Each (state, event) pair heads at most one row, so the table is a function
and emitters may key it by `(from, event)`. -/
theorem transitions_keys_nodup : (transitions.map (fun t => (t.1, t.2.1))).Nodup := by
  decide +kernel

/-! ## Every state returns to `idle` -/

/-- Release the playhead, then stop: the reset word of the player. -/
def resetWord : List UiEvent := [.scrubEnd, .stop]

/-- `resetWord` takes every state to `idle`. -/
theorem evalFrom_resetWord : ∀ s, uiDfa.evalFrom s resetWord = .idle := by decide

/-- Every state reaches `idle`: some word takes it there (`resetWord` for all). -/
theorem reaches_idle (s : UiState) : ∃ w, uiDfa.evalFrom s w = .idle :=
  ⟨resetWord, evalFrom_resetWord s⟩

/-! ## Scrubbing ends in `paused`

Precisely: from `scrubbing`, `scrubEnd` leads to `paused` and every other event
keeps `scrubbing` (`step_scrubbing`). Along any word, the state stays
`scrubbing` up to the first `scrubEnd` (`evalFrom_scrubbing`) and is `paused`
right after it (`scrubbing_ends_in_paused`). -/

/-- The step from `scrubbing`: `paused` on `scrubEnd`, `scrubbing` on every other
event. -/
theorem step_scrubbing (e : UiEvent) :
    uiDfa.step .scrubbing e = if e = .scrubEnd then .paused else .scrubbing := by
  cases e <;> rfl

/-- Every event from `scrubbing` leads to `scrubbing` or `paused`. -/
theorem step_scrubbing_mem (e : UiEvent) :
    uiDfa.step .scrubbing e = .scrubbing ∨ uiDfa.step .scrubbing e = .paused := by
  cases e <;> decide

/-- `scrubEnd` leads from `scrubbing` to `paused`. -/
theorem step_scrubbing_scrubEnd : uiDfa.step .scrubbing .scrubEnd = .paused := rfl

/-- A word free of `scrubEnd` keeps `scrubbing` in `scrubbing`. -/
theorem evalFrom_scrubbing :
    ∀ w : List UiEvent, .scrubEnd ∉ w → uiDfa.evalFrom .scrubbing w = .scrubbing
  | [], _ => rfl
  | e :: w, h => by
    rw [List.mem_cons, not_or] at h
    rw [DFA.evalFrom_cons, step_scrubbing, ite_eq_right (Ne.symm h.1)]
    exact evalFrom_scrubbing w h.2

/-- Scrubbing ends in `paused`: from `scrubbing`, the first `scrubEnd` of a word
lands in `paused`, and the rest of the word runs from there. -/
theorem scrubbing_ends_in_paused (w v : List UiEvent) (h : .scrubEnd ∉ w) :
    uiDfa.evalFrom .scrubbing (w ++ .scrubEnd :: v) = uiDfa.evalFrom .paused v := by
  rw [DFA.evalFrom_of_append, evalFrom_scrubbing w h, DFA.evalFrom_cons]
  rfl

end BioMech.Ui
