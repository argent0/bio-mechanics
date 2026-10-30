# Handover: Bio-Mechanics Explorer

Status as of 2026-10-29: the first slice (walking, right lower limb) is built, proved, tested, and live at https://argent0.github.io/bio-mechanics/. The section **Status** below describes the merged code; the sections after it keep the original design record.

## Status (end of Wave 4, 2026-10-29)

Repository: https://github.com/argent0/bio-mechanics. Site: https://argent0.github.io/bio-mechanics/ (routes `#/` explore, `#/walking` movement view, `#/architecture`). Task board: `TASKS.md`. Decisions: `DECISIONS.md` (D-001 … D-006). Module map: `spec/BioMech/Architecture.lean`, drawn by `cd spec && lake exe arch print --detail 2` or `python -m tools.arch watch`.

**New jargon**

| Term | Meaning |
|---|---|
| **Gate** | `scripts/gate.sh`: Lean build with zero `sorry`, regenerate-and-diff, ownership check, `checkGraph`/`conform` on fixtures, mypy, tsc, web tests with a recorded trace through `conform`, pytest, and the OpenSim tests when the pipeline env exists. CI (`.github/workflows/ci.yml`) runs the same checks plus the full pipeline. |
| **Role floor** | The activation a muscle needs in a phase to earn a role (D-006): phase mean ≥ 0.015 and (≥ 0.05 or ≥ 25 % of its own stride peak). |
| **Teaching example** | A biomechanics fact the app shows and a pipeline test pins exactly, e.g. the vasti braking knee flexion in loading response. |

**Lean specification (`spec/`)** — 84 theorems in the specification modules, listed with source locations in `generated/architecture.json`; all proofs by `decide`, `rfl`, `simp`, or short tactic proofs, zero `sorry`, zero `native_decide`.
- `Schema.lean`: the schema quiver (9 kinds, 12 arrows; `precedes` links each phase to the next, labelled by the gait event between them) and attribute structures, read by reflection.
- `GaitFsm.lean`, `UiFsm.lean`: the gait DFA (seven phases plus `invalid`, D-001) and the UI DFA, with stride, reachability, and scrubbing theorems.
- `Pipeline.lean`, `Components.lean`, `Acyclic.lean`: the 9-stage pipeline DAG with its artefact contract and topological order, the component import DAG with layering theorems.
- `CheckGraph.lean`, `Conform.lean`: `lake exe checkGraph` (a passing graph carries a prefunctor into the schema quiver) and `lake exe conform` (trace format C7, soundness lemmas).
- `Gen/`: `lake exe gen` writes every file under `generated/`; `Architecture.lean` + `Arch/`: `lake exe arch check | export | print`.

**Pipeline (`pipeline/`)** — `ninja -f generated/pipeline.ninja` runs all 9 stages in about 25 s with the env from `pipeline/env/setup.sh` (OpenSim 4.6, Python 3.12).
- Data: the scaled Rajagopal model and one walking trial (`pipeline/env/fetch_data.sh`), Uberon subset (committed) and FMA subset (local, licence) via `data/raw/ontology/fetch.sh`.
- Output (committed, 2.1 MB): `data/out/graph.json` (108 nodes, 557 edges), `data/out/meshes/` (13 bodies, glTF), `data/out/muscle_paths.json` (80 muscles, 50 Hz, stride bounds).
- Roles follow D-002 (moment share) with the D-006 floor. Teaching examples pinned by tests: vasti eccentric antagonists of knee flexion in loading response; semimembranosus and gluteus maximus driving hip extension; calf eccentric antagonists of ankle dorsiflexion in mid-stance; gluteus medius and minimus stabilising the hip in mid-stance; tibialis anterior active after initial contact.
- Investigation K12 confirmed stages 1–3 against inverse dynamics (knee extensor peak −0.75 N·m/kg) and the trial's EMG timing; static optimisation gives no co-contraction in early loading response, a property of its minimum-activation cost.

**Web app (`web/`)** — Vite + TypeScript (strict) + Three.js + Cytoscape.js; 60 web tests; import boundaries from the component DAG checked by `tests/test_boundaries.py`.
- GraphStore → QueryEngine → GraphView, Timeline, Viewer3D (bone glTF, muscle tubes coloured by activation, hue by braking/driving/holding), PhasePanel (roles in plain language, common and anatomical names), ArchitectureView (four diagrams, theorems with links to Lean source).
- Dev mode records FSM traces (`window.__bmTrace`); a recorded browser session lives in `data/fixtures/trace.walking-session.json` and conforms.

**Known limits**
- One subject, one trial; the left foot leaves the force plates before 0.40 s and after 1.98 s, so left-leg events there come from markers.
- The graph covers the right lower limb and pelvis; the viewer draws all 80 muscles and selects the 40 right-leg ones.
- Solver drift across machines changes up to about 2 % of edges (CI compares with `scripts/compare_graph.py`); three roles sit within 10 % of a threshold: gluteus maximus 1 as a mid-stance stabiliser of hip abduction (mean 0.103 against 0.1), and gluteus medius 1 and semitendinosus near the 0.05 helper share in loading-response hip extension.
- 16 anatomy entities have no Uberon or FMA identifier.

## Jargon

| Term | Meaning |
|---|---|
| **Knowledge graph** | Data stored as nodes (e.g. *gluteus medius*, *femur*) and labelled edges (e.g. `gluteus medius —insertion→ femur`). |
| **Ontology** | A curated, standardised anatomy vocabulary. Here: **FMA** (Foundational Model of Anatomy) and **Uberon**. |
| **Musculoskeletal model** | A computational description of bones, joints (axes, ranges), and muscle paths. We use **OpenSim** models. |
| **Rajagopal model** | The open full-body OpenSim model (Rajagopal et al., 2016; file name `Rajagopal2015`), with detailed lower-limb muscles. |
| **Moment arm** | The lever distance between a muscle's line of pull and a joint axis. Its sign gives the direction of the action (e.g. flexion vs extension). |
| **Static optimisation** | An OpenSim tool that estimates each muscle's activation at every frame of a recorded motion. |
| **Muscle activation** | A value in 0–1 for how strongly a muscle is switched on. |
| **Joint action** | One joint moving about one axis, e.g. *knee flexion*. |
| **Whole movement** | A recognisable activity composed of joint actions, e.g. *walking*, *plié*. |
| **Agonist / antagonist / stabiliser** | The muscle driving an action, the muscle opposing it, and the muscle holding a joint steady. |
| **Concentric / eccentric** | Muscle work while shortening, and muscle work while lengthening under load (braking). |
| **Gait cycle** | One stride: from initial contact of one foot to the next initial contact of the same foot. |
| **Stance / swing** | The foot on the ground (≈60% of the cycle), and the foot in the air (≈40%). |
| **Lean 4** | A programming language and proof assistant. |
| **Mathlib** | Lean's mathematics library. Supplies `DFA`, `Quiver`, `Prefunctor`, `Digraph`, `Relation.TransGen`. |
| **Lake** | Lean's build tool. `lake exe <name>` runs a Lean executable. |
| **DFA** | Deterministic finite automaton (`Mathlib.Computability.DFA`): `step : σ → α → σ`, `start : σ`, `accept : Set σ`. |
| **Quiver** | Mathlib's directed multigraph (`Mathlib.Combinatorics.Quiver.Basic`). |
| **Prefunctor** | A map between quivers that sends vertices to vertices and arrows to arrows. |
| **Digraph** | Mathlib's directed graph given by an adjacency relation (`Mathlib.Combinatorics.Digraph.Basic`). |
| **Codegen** | A Lean executable that emits TypeScript, Python, JSON, build files, and diagrams from Lean definitions. |
| **Trace conformance** | Checking that a runtime-recorded event sequence is a word accepted by the Lean DFA. |
| **glTF** | The web-standard 3D asset format, rendered by Three.js. |

## Goal

A web app where people study how the human body produces movement. A user picks a movement and sees which joints act, which muscles drive, brake, or stabilise them, and which bones and ligaments are involved, through a queryable graph, diagrams, and animation.

## Audience

People who move: dancers, athletes, sports enthusiasts. Consequences for design:

- **Movement-first entry.** Users start from "walking" or "plié", then drill into joint actions, then muscles, then bones.
- **Two names for everything.** Common name ("quads", "calf") beside the anatomical name.
- **Roles over raw numbers.** Muscles appear as *main mover / helper / stabiliser*, with numeric curves one click away.
- **Phase-aware animation.** Muscles coloured by activation, with hue showing concentric vs eccentric work, on a scrubbable timeline.
- **Later:** stretch / strengthen exercise links per muscle, as extra graph edges.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | The musculoskeletal model is the source of truth for movement facts. | Muscle roles come out of moment arms and activations, so every claim traces back to model output. |
| D2 | First slice covers the lower body. | It matters most to dancers and athletes, and the Rajagopal model is richest there. |
| D3 | First movement is **walking**. | Universal, and it shows phases, eccentric braking, and stabilisers. The Rajagopal model distribution includes walking data. |
| D4 | **Fully static app.** Python precomputes everything; the browser loads JSON + glTF and answers graph queries in memory. | Free hosting (e.g. GitHub Pages), simple to run. |
| D5 | **The architecture is written in Lean 4 with Mathlib**, and code is derived from it. | One formal architecture of record, with machine-checked properties. |
| D6 | **Hybrid Lean reach.** Lean generates types, FSM tables, pipeline order, import-boundary rules, and diagrams. Python numerics and Three.js rendering are hand-written against the generated interfaces. | Strong guarantees where structure lives, ordinary tooling where numerics and graphics live. |
| D7 | The architecture is **observable**: an in-app `/architecture` page plus runtime trace conformance. | The director can inspect the architecture and see the running app follow it. |
| D8 | Muscles are drawn as tubes along their OpenSim path points. | Matches the physics exactly and reads clearly. Sculpted muscle meshes are a possible later visual upgrade. |

Guiding rule (from `CLAUDE.md`): source code is the single source of truth, then source comments, then documentation. Here the Lean package is the top of that chain for architecture.

## Architecture

### 1. Lean specification (`spec/`)

**Knowledge-graph schema as a Quiver.** Node kinds are the vertices; allowed relations are the arrows.

```lean
inductive Kind
  | bone | joint | muscle | muscleGroup | ligament | nerve
  | movement | phase | jointAction

inductive SchemaArrow : Kind → Kind → Type
  | origin     : SchemaArrow .muscle .bone
  | insertion  : SchemaArrow .muscle .bone
  | crosses    : SchemaArrow .muscle .joint
  | partOf     : SchemaArrow .muscle .muscleGroup
  | innervatedBy : SchemaArrow .muscle .nerve
  | stabilises : SchemaArrow .ligament .joint
  | articulates : SchemaArrow .joint .bone
  | hasPhase   : SchemaArrow .movement .phase
  | involves   : SchemaArrow .phase .jointAction
  | actionAt   : SchemaArrow .jointAction .joint
  | drivenBy   : SchemaArrow .jointAction .muscle

instance : Quiver Kind := ⟨SchemaArrow⟩
```

A data graph is well-typed when it carries a `Prefunctor` into the schema quiver. `lake exe checkGraph graph.json` builds that prefunctor from the pipeline output and reports any edge that lacks a matching schema arrow.

Edge attributes (role, contraction type, activation curve, moment-arm curve) are declared as Lean structures next to their arrows, and the codegen emits them as typed fields.

**Gait cycle as a Mathlib `DFA`.** States are the gait phases plus an `invalid` sink state, which keeps `step` total. Events follow the standard phase boundaries:

| From phase | Event | To phase |
|---|---|---|
| terminal swing | `initialContact` | loading response |
| loading response | `oppositeToeOff` | mid-stance |
| mid-stance | `heelOff` | terminal stance |
| terminal stance | `oppositeInitialContact` | pre-swing |
| pre-swing | `toeOff` | initial swing |
| initial swing | `feetAdjacent` | mid-swing |
| mid-swing | `tibiaVertical` | terminal swing |

Every other (state, event) pair goes to `invalid`. Initial contact is treated as the instant opening loading response; whether it gets its own short state is an open detail (see Open items). Theorem to prove: the one-stride event word returns the automaton to its start state, and every phase is reached along the way.

**UI as a second `DFA`.** States such as `idle`, `playing`, `paused`, `scrubbing`, `inspectingNode`, with events from user input. Theorem examples: every state reaches `idle`; `scrubbing` always ends in `paused`.

**Build pipeline as a `Digraph`.** Stages:

```
loadModel → runStaticOpt → computeMomentArms → segmentPhases → labelRoles
          → enrichAnatomy → exportGraph
loadModel → exportMeshes
computeMomentArms, runStaticOpt → exportMusclePaths
```

Acyclicity is defined as irreflexivity of `Relation.TransGen adj` and proved by `decide` over the finite stage type. A topological order is computed in Lean and emitted as the build script.

**Front-end components as a `Digraph`.** Modules: `GraphStore`, `QueryEngine`, `Timeline`, `Viewer3D`, `PhasePanel`, `GraphView`, `ArchitectureView`. Edges are allowed imports. Theorems: acyclic; layering rules such as "`Viewer3D` reaches `GraphStore` only through `QueryEngine`".

**Decidability note.** Mathlib's `DFA.accept` is a `Set σ`. We supply `DecidablePred (· ∈ accept)` and `Fintype`/`DecidableEq` instances for the phase and event types so the generator and the conformance checker can run the automata.

### 2. Codegen (`lake exe gen`)

| Output | Location | Derived from |
|---|---|---|
| Node/edge types | `generated/ts/types.ts`, `generated/py/schema.py` | Schema quiver + attribute structures |
| Gait FSM tables | `generated/ts/gaitFsm.ts`, `generated/py/gait_fsm.py` | Gait DFA |
| UI FSM tables | `generated/ts/uiFsm.ts` | UI DFA |
| Pipeline build file | `generated/pipeline.ninja` | Pipeline Digraph + topological order |
| Import-boundary rules | `generated/eslint-boundaries.json` | Component Digraph |
| Architecture model | `generated/architecture.json` | All of the above, with theorem names and source locations |
| Diagrams | `generated/diagrams/*.mmd`, `*.dot` | All of the above |

Each generated file starts with a header naming its Lean source and the regeneration command. Generated files are committed; CI regenerates them and fails on any diff. `tsc` and `mypy` hold hand-written code to the generated types.

### 3. Data pipeline (`pipeline/`, Python)

Runs offline via `generated/pipeline.ninja`.

1. **loadModel**: load the Rajagopal model and the walking trial with the OpenSim Python API.
2. **runStaticOpt**: muscle activations per frame.
3. **computeMomentArms**: moment arm and muscle-tendon length per muscle, per joint coordinate, per frame. Length velocity gives concentric vs eccentric.
4. **segmentPhases**: detect gait events from the kinematics and ground contact, then drive the generated gait FSM to label each frame with a phase.
5. **labelRoles**: per phase and joint action, classify each muscle as main mover / helper / stabiliser / antagonist from moment-arm sign and activation. Thresholds live in one config file and are recorded in the output.
6. **enrichAnatomy**: add common names, attachments, and innervation from Uberon/FMA subsets plus a small hand-curated YAML file.
7. **exportGraph / exportMeshes / exportMusclePaths**: `data/out/graph.json`, bone glTF files from the model's `.vtp` geometry, and muscle path points per frame.

### 4. Web app (`web/`, TypeScript)

Proposed stack: Vite, TypeScript, Three.js, Cytoscape.js.

- **Search**: "walking" opens the movement view.
- **Timeline**: scrubbable gait cycle with phase bands, driven by the generated UI and gait FSMs.
- **Viewer3D**: skeleton playing the walking trial; muscles as tubes, coloured by activation, hue by concentric/eccentric.
- **PhasePanel**: for the current phase, joint actions and their muscles in plain language with roles.
- **GraphView**: click any node to explore its neighbours.
- **ArchitectureView** (`/architecture`): renders `generated/architecture.json` (schema quiver, both FSMs, pipeline DAG, component DAG), each linked to Lean source and theorems. In dev mode it highlights live FSM states.

### 5. Observability

- **Static**: `/architecture` page, Mermaid/DOT diagrams, and `doc-gen4` docs of the Lean package.
- **Runtime**: in dev mode the app records FSM event traces to `trace.json`. `lake exe conform trace.json` confirms each trace is accepted by its DFA.

## Proposed repository layout

```
bio-mechanics/
├── CLAUDE.md
├── handover.md
├── prompt.md
├── spec/                    Lean package (architecture of record)
│   ├── lakefile.lean
│   ├── lean-toolchain       pinned to the toolchain Mathlib expects
│   └── BioMech/
│       ├── Schema.lean      Kind, SchemaArrow, attribute structures
│       ├── GaitFsm.lean     gait DFA + theorems
│       ├── UiFsm.lean       UI DFA + theorems
│       ├── Pipeline.lean    stage Digraph, acyclicity, topological order
│       ├── Components.lean  module Digraph, layering theorems
│       ├── Acyclic.lean     shared acyclicity definitions and lemmas
│       ├── Gen/             emitters: TS, Python, ninja, eslint, JSON, Mermaid/DOT
│       ├── CheckGraph.lean  prefunctor check of graph.json
│       └── Conform.lean     trace conformance checker
├── generated/               output of `lake exe gen` (committed)
├── pipeline/                Python data pipeline
├── data/
│   ├── raw/                 OpenSim model, walking trial, ontology subsets
│   └── out/                 graph.json, glTF, muscle paths
└── web/                     Vite + TypeScript app
```

## Data sources

| Source | Use | Licence to confirm |
|---|---|---|
| Rajagopal OpenSim model + walking trial (SimTK) | Geometry, muscles, motion, activations | SimTK project terms |
| Uberon | Anatomy terms, part-of relations | CC-BY 3.0 |
| FMA | Attachments, innervation detail | FMA licence terms |
| Z-Anatomy / BodyParts3D | Future sculpted meshes | CC-BY-SA |

## Environment (checked 2026-10-29)

| Tool | State |
|---|---|
| Lean 4.35.0 via elan, Lake | installed |
| Python 3 | installed |
| Node | installed |
| OpenSim Python bindings | to install, e.g. `conda install -c opensim-org opensim` |
| Git | the directory is ready for `git init` |

Mathlib setup: add it as a Lake dependency, set `lean-toolchain` to Mathlib's, then `lake exe cache get` for prebuilt binaries.

## Next steps

1. Later movements (squat, plié, relevé, jump), in the order the director sets: a trial per movement through the same pipeline, a movement node per trial.
2. Stretch and strengthen exercise links per muscle, as extra graph edges (Audience, "Later").
3. Optional: EMG-informed optimisation for co-contraction in early stance (K12, proposal 4).
4. Optional: `supportInterpreter := true` on `lean_exe gen` (K2), and a dagre layout for the architecture diagrams.

## Open items for the director

- Order of later movements after walking (e.g. squat, plié, relevé, jump).
