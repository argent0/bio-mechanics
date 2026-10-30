# Task board

Sole writer: the coordinator. Source plan: `plan.md`. Module ownership: `spec/BioMech/Architecture.lean`.

States: `todo` · `running` · `review` · `merged`. Fails: gate rounds failed by the current worker.

## Wave 0 — Foundation (coordinator)

| Task | Owner | Model | State | Output | Acceptance |
|---|---|---|---|---|---|
| 0.1 Repository skeleton, `.gitignore`, `TASKS.md`, baseline test | coordinator | opus | merged | repository, `scripts/gate.sh`, `tests/test_fixture.py` | gate passes |
| 0.2 Lean package, Mathlib `v4.35.0`, `lake exe cache get` | coordinator | opus | merged | `spec/lakefile.lean`, `spec/lean-toolchain` | `lake build` |
| 0.3 `Schema.lean`: `Kind`, `SchemaArrow`, `Quiver`, attribute structures | coordinator | opus | merged | **C1** | `lake build` |
| 0.3a Module map + `lake exe arch check / export / print` | coordinator | opus | merged | **C4** `generated/modules.json` | `arch check`; `arch print --detail 1` |
| 0.4 `lake exe gen`: `types.ts`, `schema.py` by reflection over C1 | coordinator | opus | merged | **C2** | regenerate gives an empty diff |
| 0.5 Fixture `data/fixtures/graph.sample.json` | coordinator | opus | merged | **C3** fixture, 24 nodes, 51 edges | `pytest tests/test_fixture.py` |
| 0.6 Director: initial contact as a DFA state or an instant | coordinator | opus | todo | `DECISIONS.md` | answer before A starts |

## Wave 1

| ID | Workstream | Model / effort | Worker ID | Fails | State | Branch | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|---|---|---|---|
| A | Lean FSMs | opus / xhigh | — | 0 | todo | `ws/A` | C1, decision 0.6 | `GaitFsm.lean`, `UiFsm.lean` | `lake build`, zero `sorry` |
| B | Lean graphs | opus / xhigh | — | 0 | todo | `ws/B` | C1 | `Pipeline.lean`, `Components.lean`, `Acyclic.lean` | `lake build`, zero `sorry` |
| D | Data acquisition | sonnet / high | — | 0 | todo | `ws/D` | — | `pipeline/env/`, `data/raw/` | `python -c "import opensim"` loads model and trial |
| E | Web scaffold | sonnet / medium | — | 0 | todo | `ws/E` | C2, C3 | `web/` | `tsc` clean; `npm run build` |
| H | Arch viewer | sonnet / high | — | 0 | todo | `ws/H` | C4 | `tools/arch/` | `mypy`; `print --detail 0..3`; `svg`; watch redraw < 2 s |

## Wave 2

| ID | Workstream | Model / effort | Worker ID | Fails | State | Inputs | Acceptance |
|---|---|---|---|---|---|---|---|
| C | Emitters | opus / high | — | 0 | todo | A, B | regenerate gives an empty diff; `ninja -n` |
| P1 | Pipeline stages 1–3 | opus / high | — | 0 | todo | D, C2 | `mypy`; tibialis anterior and gluteus medius plausibility |
| F | Lean checkers | opus / high | — | 0 | todo | C1, A, C3 | fixture passes; bad edge and bad trace fail by name |
| E2 | ArchitectureView | sonnet / medium | — | 0 | todo | C (`architecture.json`) | `tsc`; four diagrams render |

## Wave 3

| ID | Workstream | Model / effort | Worker ID | Fails | State | Inputs | Acceptance |
|---|---|---|---|---|---|---|---|
| P2 | Pipeline stages 4–7 | opus / high | — | 0 | todo | P1, C, thresholds decision | `ninja`; `lake exe checkGraph data/out/graph.json` |
| E3 | Movement views | sonnet / high | — | 0 | todo | C, P2 | `tsc`, eslint boundaries; walking plays and scrubs |
| G | CI and traces | sonnet / medium | — | 0 | todo | F, C | CI green on `main` |

## Wave 4 — Integration (coordinator)

| Task | State |
|---|---|
| Replace fixture references with pipeline output | todo |
| Full gate on `main` | todo |
| Record a walking trace, pass `lake exe conform` | todo |
| Fresh `handover.md` status from merged code | todo |
| Director: order of later movements | todo |

## Escalations

| Workstream | From | To | Reason |
|---|---|---|---|

## Open items for the director

1. Initial contact: own DFA state, or an instant at the start of loading response (blocks A).
2. Role-classification thresholds (blocks P2).
3. Hosting target (blocks G deployment).
4. Order of later movements (Wave 4).
