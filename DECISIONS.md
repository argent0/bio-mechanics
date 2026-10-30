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

## D-003 — The site is hosted on GitHub Pages (2026-10-29)

**Decision:** The static site (`web/dist/`, built by `npm run build` in `web/`) is published to GitHub Pages by a deploy job in the GitHub Actions workflow, on every push to `main` once the gate jobs pass. The repository lives on GitHub; the director creates it and gives its URL.
**Terms:** *GitHub Pages* — GitHub's free static hosting, fed here by the Actions "deploy-pages" flow. *Static site* — HTML, JavaScript, JSON and glTF files served as they are; the browser answers every graph query in memory.
**Why:** Unstated by the director, who chose the coordinator's recommended option. The recommendation's reason: the CI workflow already runs on GitHub Actions, the build uses relative paths (`base: './'`), and the deploy job is a placeholder waiting to be enabled.
**Code:** `.github/workflows/ci.yml` (the commented deploy job, workstream G); `web/src/architecture/config.ts` `SOURCE_BASE_URL` takes the repository URL once it exists.

## D-004 — Roles need a minimum activation (2026-10-29)

**Decision:** Refines D-002. A muscle earns the role *main mover*, *helper* or *antagonist* for a joint action in a phase only when its mean activation over the phase is ≥ 0.05; below that floor it is *inactive* for that action and phase, and the knowledge graph carries no `drivenBy` edge for it. The *stabiliser* role keeps its own floor of activation ≥ 0.1 from D-002. The floor lives in `pipeline/config/roles.yaml` beside the D-002 thresholds, and the output records it.
**Terms:** *Mean activation over the phase* — the average of the muscle's activation (0–1) across the frames of the phase. *Inactive* — present in the model, with too little activation in the phase to count for the action. *`drivenBy` edge* — the knowledge-graph edge from a joint action to a muscle that carries the muscle's role in one phase.
**Why:** Unstated by the director, who chose the coordinator's recommended option. The recommendation's reason: under pure moment share, a near-silent muscle (tibialis anterior at mean activation 0.01 in mid-stance) became "main mover" of ankle dorsiflexion because the total moment was near zero, and the audience reads roles as effort.
**Code:** `pipeline/label_roles.py` and `pipeline/config/roles.yaml` (workstream P2); outputs `data/work/roles.json` and `data/out/graph.json`.

## D-005 — The role floor is relative to the muscle's own peak (2026-10-29)

**Decision:** Replaces D-004. A muscle earns the role *main mover*, *helper* or *antagonist* for a joint action in a phase only when its mean activation over the phase is ≥ 25 % of its own peak activation over the stride; below that floor it is *inactive* for that action and phase, and the knowledge graph carries no `drivenBy` edge for it. The *stabiliser* role keeps its floor of activation ≥ 0.1 from D-002. The fraction (0.25) lives in `pipeline/config/roles.yaml`, and the output records it.
**Terms:** *Mean activation over the phase* — the average of the muscle's activation (0–1) across the frames of the phase. *Own peak over the stride* — the largest activation the muscle reaches between the two right initial contacts that bound the stride. *Inactive* — present in the model, with too little activation in the phase, relative to its own peak, to count for the action. *`drivenBy` edge* — the knowledge-graph edge from a joint action to a muscle that carries the muscle's role in one phase.
**Why:** Unstated by the director, who chose the coordinator's recommended option. The recommendation's reason: the investigation K12 found the vasti carrying 59–109 % of the knee-extensor moment while lengthening late in loading response (eccentric braking), while D-004's absolute floor of 0.05 hid them because their phase mean (0.031) averages over a first half where the hamstrings hold a flexor moment. Relative to their own stride peak the vasti reach about 0.35; tibialis anterior in mid-stance stays near 0.03 of its peak and remains inactive. Normalising to a muscle's own peak follows the convention for electromyography.
**Code:** `pipeline/label_roles.py` and `pipeline/config/roles.yaml` (workstream P2), `pipeline/tests/test_p2_*.py`; outputs `data/work/roles.json` and `data/out/graph.json`. Contradicts D-004's floor (`roleMinActivation: 0.05` in `pipeline/config/roles.yaml`).
