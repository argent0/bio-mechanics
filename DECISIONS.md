# Decisions

## D-001 — Initial contact is an instant in the gait DFA (2026-10-29)

**Decision:** Initial contact is an instant, carried by the event `initialContact`, which moves the gait DFA from terminal swing to loading response. The gait DFA has seven phase states (loading response, mid-stance, terminal stance, pre-swing, initial swing, mid-swing, terminal swing) plus an `invalid` sink state that keeps `step` total.
**Terms:** *Gait DFA* — the deterministic finite automaton over gait events whose states are the gait phases. *Initial contact* — the moment the foot first touches the ground, opening the stance part of the gait cycle. *Loading response* — the first stance phase, from initial contact to opposite toe-off, where the leg takes the body's weight.
**Why:** The event `initialContact` already marks the moment; the timeline shows the standard seven phase bands; the pipeline labels every frame with one of seven phases.
**Code:** `spec/BioMech/GaitFsm.lean` (to be written by workstream A).

## D-002 — Muscle roles by moment share (2026-10-29)

**Decision:** Stage `labelRoles` classifies each muscle per joint action and phase by its share of moment. A muscle's moment at a frame is activation × max isometric force × moment arm about the action's coordinate. A muscle is an agonist of the action when its moment arm sign matches the action's direction and |moment arm| ≥ 5 mm; it is an antagonist when the sign is opposite. Over the phase: an agonist with ≥ 25 % of the total agonist moment is a *main mover*, one with 5–25 % a *helper*; an opposing muscle with ≥ 5 % of the total opposing moment is an *antagonist*; a muscle with activation ≥ 0.1 while the coordinate moves < 5° in the phase is a *stabiliser*. The thresholds (5 mm, 25 %, 5 %, 0.1, 5°) live in `pipeline/config/roles.yaml`, and the output records them.
**Terms:** *Joint action* — one joint moving about one axis in one direction, e.g. knee flexion. *Moment arm* — the lever distance between the muscle's line of pull and the joint axis; its sign gives the direction the muscle's force turns the joint. *Max isometric force* — the largest force the muscle model produces at optimal length and zero velocity. *Share* — the muscle's moment integrated over the phase, divided by the sum over all agonists (or all opposing muscles).
**Why:** Unstated by the director, who chose the coordinator's recommended option. The recommendation's reason: strong, small muscles rank by what they contribute to the movement, so a role reflects a muscle's mechanical contribution.
**Code:** `pipeline/label_roles.py` and `pipeline/config/roles.yaml` (workstream P2); `pipeline/config/roles.yaml` is the artefact `roleThresholds` read by stage `labelRoles` in `spec/BioMech/Pipeline.lean`.
