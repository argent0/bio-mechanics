# Bio-Mechanics Explorer

A static web app for studying how the body produces movement: pick a movement, see which joints act, which muscles drive, brake, or hold them, and which bones are involved. Live at https://argent0.github.io/bio-mechanics/.

## Jargon

| Term | Meaning |
|---|---|
| **Lean 4 / Mathlib** | A proof assistant and its mathematics library. The architecture is written and proved here. |
| **Codegen** | `lake exe gen`: writes every file under `generated/` from the Lean definitions. |
| **Gate** | `scripts/gate.sh`: the full check every commit passes. |
| **Trace conformance** | Checking that FSM events recorded in the browser form a word the Lean automaton accepts. |

## Where things live

The code is the source of truth. Each item names the file that defines it.

| What | Source |
|---|---|
| Graph schema (node kinds, relations) | `spec/BioMech/Schema.lean` |
| Gait and UI state machines | `spec/BioMech/GaitFsm.lean`, `spec/BioMech/UiFsm.lean` |
| Pipeline stages and order | `spec/BioMech/Pipeline.lean` → `generated/pipeline.ninja` |
| Front-end modules and allowed imports | `spec/BioMech/Components.lean` → `generated/eslint-boundaries.json` |
| Module ownership map | `spec/BioMech/Architecture.lean` |
| Theorems, with source locations | `generated/architecture.json`, shown at `#/architecture` |
| Pipeline scripts (OpenSim, Python) | `pipeline/` |
| Merged whole-body model: sources, body map, neck assumption | `pipeline/config/model.yaml`, `pipeline/build_model.py` |
| Body regions and curated anatomy (right side; the left side comes from code) | `data/curated/anatomy.yaml`, `pipeline/enrich_anatomy.py` |
| Role thresholds and labelled coordinates | `pipeline/config/roles.yaml` |
| Pipeline output | `data/out/` |
| Data provenance and licences | `data/raw/SOURCES.md`, `data/raw/ontology/SOURCES.md` |
| Web app (Vite, TypeScript, Three.js, Cytoscape.js) | `web/src/` |
| Decisions | `DECISIONS.md` |
| Open work | `handover.md`, `TASKS.md` |

## Commands

```sh
cd spec && lake build                     # build and check every proof
cd spec && lake exe gen                   # regenerate generated/
cd spec && lake exe checkGraph <graph>    # check a graph against the schema
cd spec && lake exe conform <trace>       # check a recorded trace against the FSMs
cd spec && lake exe arch print --detail 2 # draw the module map

pipeline/env/setup.sh                     # create the OpenSim env, print its Python
pipeline/env/fetch_data.sh                # fetch the model and walking trial
ninja -f generated/pipeline.ninja         # run the pipeline into data/out/

cd web && npm install && npm run dev      # run the app
cd web && npm test                        # web tests

scripts/gate.sh                           # everything above that CI checks
```
