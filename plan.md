# Plan: The Whole Body, Walking

Status as of 2026-10-30. Goal: extend the Explorer from the right lower limb and pelvis to the whole body (left leg, trunk, arms, head), with walking as the one movement. The work splits into workstreams that run in parallel, with one coordinator agent that owns the order, the contracts, and the merges, as in the first slice.

## Jargon

| Term | Meaning |
|---|---|
| **Coordinator** | The agent that owns the task board, assigns workstreams, merges finished work, and brings open items to the director. |
| **Worker** | An agent assigned one workstream. It works in its own git worktree and hands back a branch. |
| **Workstream** | A sequence of tasks with one owner and one set of owned paths. |
| **Wave** | A group of workstreams that run at the same time. A workstream starts once its own inputs are merged on `main`. |
| **Contract** | A file that several workstreams read and one writes, e.g. `Schema.lean` or the shape of `graph.json`. Contracts freeze before the wave that reads them. |
| **Fixture** | A small hand-made sample of a contract's output that lets readers start before the writer finishes. |
| **Worktree** | A separate checkout of the same repository (`git worktree`). |
| **Task board** | `TASKS.md`; the coordinator is its sole writer. |
| **Worker ID** | The agent ID the `Agent` tool returns at launch; `SendMessage` to it resumes the same worker. |
| **Module map** | `spec/BioMech/Architecture.lean`: modules, owned paths, and the APIs between them. |
| **Gate** | `scripts/gate.sh`, plus the workstream's own acceptance test. |
| **Green main** | `main` passing the full gate at every commit. |
| **Model tier** | The Claude model an agent runs on: Fable 5.1 (`fable`), Opus 5.5 (`opus`), Sonnet 5.5 (`sonnet`), Haiku 5.5 (`haiku`), most to least capable. |
| **Effort** | Reasoning depth per step: `low`, `medium`, `high`, `xhigh`, `max`. |
| **Escalation** | Relaunching a stuck workstream on the next tier up, with the previous report as input. |
| **Torque actuator** | An OpenSim `CoordinateActuator`: a motor that drives one joint coordinate directly. In the Rajagopal model, all lumbar, shoulder, elbow, forearm and wrist coordinates are driven this way, and every muscle sits in the legs. |
| **Reserve actuator** | A weak torque actuator that static optimisation uses for the moment the muscles leave unexplained. Small reserves mean the muscles explain the motion. |
| **Model merge** | Building one OpenSim model from the Rajagopal model plus the trunk and arm muscles of a second, muscle-driven model, attached to the matching bodies. |
| **Reference leg** | The right leg. Its seven gait phases form the one timeline for the whole body. |
| **Region** | A body part a node belongs to: `lowerLimb`, `pelvis`, `trunk`, `upperLimb`, `head`. |
| **Mirroring** | Deriving each left-side entry from its right-side entry in code: key `_r` → `_l`, side `right` → `left`, FMA term "Right …" → "Left …". |

## Starting point (from the code)

- `data/raw/rajagopal/Rajagopal2016.osim`: 22 bodies, both legs with muscles, a torso carrying the head, both arms with hands; torque actuators on `lumbar_*`, `shoulder_*`/`arm_*`, `elbow_flex_*`, `pro_sup_*`, `wrist_*`.
- The walking trial's inverse kinematics (`IK/results_walk/ik_output_walk.mot`) holds every coordinate, upper body included; the marker file holds shoulder, clavicle, elbow and wrist markers.
- `pipeline/config/roles.yaml` selects the right leg (`muscleSuffix: "_r"`, five right coordinates); `pipeline/enrich_anatomy.py` gives side `right` or `midline`; `pipeline/export_meshes.py` and `pipeline/export_dynamics.py` list right-leg bodies and muscles; `data/curated/anatomy.yaml` covers the right lower limb and pelvis.
- `Side` in `spec/BioMech/Schema.lean` already holds `left | right | midline`.

## Principles

1. **Contracts first.** The coordinator lands the schema change and the fixture on `main` before any wave fans out.
2. **One owner per file.** Shared files (contracts, `TASKS.md`, `lakefile.lean`, root config) belong to the coordinator.
3. **Fixtures unblock readers.** Web work starts on the extended fixture; real output replaces it later.
4. **Source code is the truth** (`CLAUDE.md`). Left-side anatomy comes from mirroring in code, so each fact lives once.
5. **The model is the source of movement facts** (handover D1). Every role in the trunk and arms comes from muscles in an OpenSim model.
6. **The right leg holds still.** Every right-leg role in today's `data/out/graph.json` survives, checked by `scripts/compare_graph.py` within its current tolerance.
7. **Director decisions arrive one question at a time**, at the moment a workstream needs the answer, recorded with the `decision` skill in `DECISIONS.md` (D-007 onward).
8. **The architecture is visible at all times**: each new workstream enters the module map before its code.
9. **Green main**: a new gate check lands in the same commit as the code that satisfies it.
10. **Acceptance criteria are hard numbers and exact commands.**

## Director questions, in order

| # | Asked when | Question | Coordinator's recommendation |
|---|---|---|---|
| Q1 | Wave 0, before 0.3 (answered: D-007) | Phase timeline for the whole body: the reference leg's seven phases for every muscle, or a phase set per leg | Reference leg: one timeline, one `Timeline` component, and the left leg's own phases read off as half a stride later. |
| Q2 | Wave 0, after investigation K19 (answered: D-008) | Source of trunk and arm muscles: merge a muscle-driven model (K19's pick) onto Rajagopal, or keep torque actuators and show the trunk and arms with joint moments and anatomy only | Model merge: it keeps principle 5. |
| Q3 | When P4 starts | Head and neck: head rigid with the torso (as in Rajagopal), or a neck with muscles | Answered: neck with muscles (D-009). |
| Q4 | When M starts (answered: D-010, head level) | Neck motion: the trial's markers stop at the shoulders and clavicles, so neck angles come from an assumption. Hold the head level in the ground frame (neck angles from the torso's motion), or hold the neck at its static-pose angle | Head level: walkers keep gaze and head steady, so neck muscles show the work of steadying the head. |

## Roles

### Coordinator (one agent, the whole project)

- Runs Wave 0 and Wave 3 personally.
- Adds a section **Whole body** to `TASKS.md`; the first slice's sections stay as history.
- Creates each worktree (`git worktree add ../bm-<ID> -b ws/<ID>`) and puts its absolute path in the brief.
- Adds each workstream's module to the module map and commits it on `main` before launch.
- Reviews each branch: `git diff --name-only main...<branch>` lists only owned paths, and the gate passes in the worktree; then merges, runs `lake exe gen`, reruns the gate on `main`, and commits.
- Changes a frozen contract only through a coordinator task, then re-briefs affected workers.
- Keeps waves at five workers or fewer.

### Workers

- First report `pwd`, `git rev-parse --show-toplevel`, and `git branch --show-current`.
- Work inside their owned paths and worktree.
- Finish with a report: branch, what passes, what remains, proposed contract changes.

## Model selection

Rule: the tier follows the hardest reasoning in the task. Proofs, contracts, model building and biomechanics correctness go to Opus 5.5; application code and tooling to Sonnet 5.5; lookups and log triage to Haiku 5.5; Fable 5.1 is the escalation tier.

| Agent | Model | Effort | Reason |
|---|---|---|---|
| Coordinator | `opus` | `high` | Contract design, reviews, the whole project in mind. |
| **K19** Upper-body model survey | `opus` | `high` | Judges model quality, licences, and fit with Rajagopal's bodies. |
| **S** Lean spec additions | `opus` | `xhigh` | New stages, components and theorems with proofs by `decide`. |
| **L** Left leg | `opus` | `high` | Roles and teaching examples on a second side. |
| **M** Model merge | `opus` | `xhigh` | Attaching foreign muscles to Rajagopal bodies and tuning reserves. |
| **P4** Trunk and arm stages | `opus` | `high` | Roles and teaching examples for new regions. |
| **D2** Upper-body data | `sonnet` | `high` | Fetch, checksum, licence notes, env check. |
| **W1** Web, whole-body views | `sonnet` | `high` | Three.js framing, regions, filters on a fixture. |
| **W2** Web, real output | `sonnet` | `medium` | Wiring and performance on the real graph. |
| **G2** CI | `sonnet` | `medium` | Workflow changes for the new data and stages. |
| Lookups and log triage | `haiku` | `low` | Searches and log summaries for the coordinator. |
| Escalation of any Opus workstream | `fable` | `high` | For proofs or numerics that resist two Opus rounds. |

A Haiku or Sonnet worker that fails its gate twice escalates one tier up; an Opus worker escalates to Fable. Each escalation goes into `TASKS.md` with from-tier, to-tier and reason. Escalation brief: the previous report, every failing gate output, the same worktree and branch, and the owned paths restated.

## Waves

### Wave 0 — Foundation (coordinator, serial, plus K19 in parallel)

| Task | Output | Acceptance |
|---|---|---|
| 0.1 `TASKS.md` section **Whole body** with every task of this plan | task board | each task has owner, model, state, inputs, outputs, acceptance |
| 0.2 Launch **K19** (read-only survey, see below) | K19 report | report in hand before Q2 |
| 0.3 Ask Q1; record D-007 | `DECISIONS.md` | answer before 0.4 |
| 0.4 Contract C1: `Region` enum and a `region` field in `NodeAttrs`; a theorem that every `Kind` used for anatomy carries a region | `spec/BioMech/Schema.lean` | `lake build`, zero `sorry` |
| 0.5 Contract C2: regenerate | `generated/ts/types.ts`, `generated/py/schema.py` | regenerate gives an empty diff |
| 0.6 Contract C3: extend the fixtures with a left knee, the lumbar joint, a right shoulder and elbow, and their muscles | `data/fixtures/graph.sample.json`, `graph.bad-edge.json` | between 40 and 50 nodes; `lake exe checkGraph` passes the sample and names the bad edge |
| 0.7 Q2 answered (D-008); the coordinator confirms K19's picks against D-008 | K19 picks in `TASKS.md` | picks in hand before D2 starts |

**K19 — Upper-body model survey.** Candidates to assess include the Christophy 2012 lumbar spine model, the Raabe & Chaudhari 2016 full-body lumbar spine model (built on Rajagopal), the Holzbaur 2005 upper-extremity model, MoBL-ARMS (Saul 2015), and for the neck (D-009) the Vasavada 1998 head-neck model and its successors. Per candidate: licence, OpenSim 4.6 load test, muscle count per region, body and joint names against Rajagopal's `torso`, `humerus_*`, `ulna_*`, `radius_*`, `hand_*`, and the work a merge needs, including splitting the head from `torso`. Output: a ranked table with one pick per region (trunk, arm, neck) and the reason, in the K19 report. Model `opus`, effort `high`.

### Wave 1 — Five parallel workstreams

| ID | Workstream | Owned paths | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|
| **S** | Lean spec additions | `spec/BioMech/Pipeline.lean`, `Components.lean`, `Gen/` | C1, D-008 | stage `buildModel` before `loadModel` (when D-008 is the merge); component `RegionFilter` between `QueryEngine` and the views; emitters for the region enum | acyclicity and layering theorems hold; zero `sorry`; `ninja -n -f generated/pipeline.ninja` accepts the new stage |
| **L** | Left leg | `pipeline/label_roles.py`, `enrich_anatomy.py`, `export_*.py`, `pipeline/config/roles.yaml` | C1–C3, D-007 | roles for both legs on the reference timeline; left anatomy by mirroring; left bodies in meshes, paths and dynamics | 40 left-leg muscles in `graph.json`, equal to the right; `compare_graph.py` shows the right leg unchanged; mirrored teaching examples pass, e.g. left vasti eccentric antagonists of knee flexion in the reference phase that holds left loading response; `checkGraph` passes |
| **D2** | Upper-body data | `data/raw/<D-008 model>/`, `pipeline/env/` | D-008 | fetch script, `SHA256SUMS` entries, a `SOURCES.md` section with licence terms | `pipeline/env/check_env.py` loads the model in OpenSim 4.6 |
| **W1** | Web, whole-body views | `web/src/viewer/`, `phase/`, `graphview/`, `web/src/region/` | C2, C3 fixture | viewer frames the whole skeleton, head and hands included; region and side filter; `PhasePanel` and the dynamics panel grouped by region and side; search across regions | `tsc` clean; web tests pass; boundary test passes with `RegionFilter` once S merges |
| **G2** | CI | `.github/workflows/` | D2 | CI fetches and caches the upper-body model; pipeline job runs every stage | CI green on `main`; pipeline job under 15 minutes |

Wave 1 sizing: K19 finishes in Wave 0, so five workers run here. D2 starts once D-008 is recorded; L, W1 and S's component part start at once.

### Wave 2 — Three parallel workstreams

| ID | Workstream | Owned paths | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|
| **M** | Model merge | `pipeline/build_model.py`, `pipeline/static_opt.py`, `pipeline/config/model.yaml` | D2, S (`buildModel` stage), D-008, D-009, D-010 | one model with leg, trunk, arm and neck muscles; the head split from `torso` with a neck joint (D-009) and neck angles holding the head level in space (D-010); muscles replace the torque actuators on the coordinates they span; reserves on every coordinate | model loads; static optimisation completes over the stride; reserve moments under 10 N·m RMS on lumbar coordinates, under 2 N·m RMS on arm coordinates and under 1 N·m RMS on neck coordinates; leg activations change by under 0.02 RMS from today's run |
| **P4** | Trunk and arm stages | `pipeline/label_roles.py`, `enrich_anatomy.py`, `export_*.py`, `pipeline/config/roles.yaml`, `data/curated/anatomy.yaml` (takes these over from L once L merges) | M, L, D-009 | roles for neck, lumbar, shoulder, elbow, forearm and wrist actions; curated anatomy for neck, trunk, arms and head with Uberon and FMA ids; meshes for torso, head, arms and hands | teaching examples pinned by tests: erector spinae active within 10 % of the stride around each initial contact (two bursts per stride); posterior deltoid active during the arm's backward swing; neck extensors (e.g. splenius capitis) stabilising the head in at least one phase; a test that records which arm muscles fall below the D-006 floor; `checkGraph` passes |
| **W2** | Web, real output | `web/src/` (the paths W1 owned) | P4 output, S | real graph wired in; muscle tubes for every muscle | viewer holds 30 fps or more with every muscle drawn on the director's machine; `data/out/` stays under 8 MB; a recorded session trace conforms |

### Wave 3 — Integration (coordinator)

- Replace every fixture reference with real output; run the full gate on `main`.
- Record a whole-body walking trace in dev mode; `lake exe conform` accepts it.
- Update `README.md` pointers and `handover.md` (open work and known limits only).
- Deploy to GitHub Pages and check `#/walking` shows both legs, trunk and arms.

## Dependency graph

```
Wave 0 (coordinator): Q1 → C1 Region → C2 types → C3 fixture       K19 survey → Q2
                         │                                              │
   ┌───────────────┬─────┴──────────┬────────────────┐                  │
   L Left leg      W1 Web views     S Lean additions D2 Upper data ─────┘
   │               │                │                │       G2 CI
   │               │                └──────┬─────────┘
   │               │                       M Model merge
   └───────────────┼───────────────────────┤
                   │                       P4 Trunk and arms (Q3)
                   └───────────┬───────────┘
                               W2 Web, real output
                               │
                    Wave 3 Integration
```

## Coordinator brief

The director starts the coordinator on Opus 5.5 (`claude --model opus`, effort `high`) with:

> You are the coordinator for the Bio-Mechanics Explorer. Read `CLAUDE.md`, `README.md`, `handover.md`, `DECISIONS.md`, and `plan.md` in `/home/aner/software/bio-mechanics`. Follow `plan.md`.
>
> 1. Run Wave 0 yourself and launch K19 at its start. Add the section **Whole body** to `TASKS.md` with every task of `plan.md`; you are its sole writer.
> 2. For each workstream: add its module to the module map and commit on `main`; create its worktree; launch workers together in one message with the `model` and `effort` from the Model selection table; record each worker ID in `TASKS.md`. Each brief states: the absolute worktree path, owned paths, input contracts with their paths on `main`, outputs, the acceptance test with hard numbers, the gate steps owned by others, and the rules "first report `pwd`, repository root, and branch; work inside your owned paths; report proposed contract changes to the coordinator".
> 3. When a worker returns, check `git diff --name-only main...<branch>` against its owned paths and run the gate in its worktree. A passing branch merges to `main`; then run `lake exe gen`, rerun the gate, and commit. A failing branch goes back to the same worker ID via `SendMessage` with the exact failing output, and its failure count goes up by one. At two failures, escalate.
> 4. Start each workstream as soon as its own inputs are merged.
> 5. Ask the director the questions Q1–Q3 one at a time, at the moment each blocks work. Record each answer with the `decision` skill.
> 6. After each merge, post a two-line status: what merged, what runs now.
> 7. Commit with the `commit` skill.

## Risks and responses

| Risk | Response |
|---|---|
| The chosen upper-body model names bodies differently from Rajagopal | M maps bodies in `pipeline/config/model.yaml` and checks every muscle path point lands on an existing body. |
| Merged muscles leave large reserves | M tunes path points and optimal fibre lengths within the source model's ranges; past two rounds the coordinator opens an investigation (K20) and asks the director. |
| Static optimisation shows arm swing as nearly passive | That is a known feature of walking; P4 records it in a test and the app shows it as a teaching example. |
| The trial has head markers for zero frames, so neck angles rest on D-010's assumption | M pins the assumption in `pipeline/config/model.yaml` and its code comments; the app labels neck roles as resting on it. |
| The left foot stands on a force plate from 0.84 s to 1.59 s only | L takes the left events outside that window from markers and pins the method in code comments (done). |
| Many more tubes slow the viewer | W2 merges tube geometry per region and measures frame rate in its acceptance test. |
| Right-leg roles drift through the merged model | Principle 6: `compare_graph.py` gates every merge into `main`. |
| Token spend grows with the workstream count | Web, CI and data work run on Sonnet 5.5; lookups on Haiku 5.5; Fable 5.1 only on escalation. |

## Later

Further movements (order deferred by the director), exercise links per muscle, sculpted muscle meshes: see `handover.md`.
