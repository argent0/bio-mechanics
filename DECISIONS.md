# Decisions

## D-001 — Initial contact is an instant in the gait DFA (2026-10-29)

**Decision:** Initial contact is an instant, carried by the event `initialContact`, which moves the gait DFA from terminal swing to loading response. The gait DFA has seven phase states (loading response, mid-stance, terminal stance, pre-swing, initial swing, mid-swing, terminal swing) plus an `invalid` sink state that keeps `step` total.
**Terms:** *Gait DFA* — the deterministic finite automaton over gait events whose states are the gait phases. *Initial contact* — the moment the foot first touches the ground, opening the stance part of the gait cycle. *Loading response* — the first stance phase, from initial contact to opposite toe-off, where the leg takes the body's weight.
**Why:** The event `initialContact` already marks the moment; the timeline shows the standard seven phase bands; the pipeline labels every frame with one of seven phases.
**Code:** `spec/BioMech/GaitFsm.lean` (to be written by workstream A).
