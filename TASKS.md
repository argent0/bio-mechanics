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
| 0.6 Director: initial contact as a DFA state or an instant | coordinator | opus | merged | `DECISIONS.md` D-001: an instant | answer before A starts |

## Wave 1

| ID | Workstream | Model / effort | Worker ID | Fails | State | Branch | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|---|---|---|---|
| A | Lean FSMs | opus / xhigh | `ae7b4cbffa4f406b3` | 0 | merged | `ws/A` | C1, decision 0.6 | `GaitFsm.lean`, `UiFsm.lean` | `lake build`, zero `sorry` |
| B | Lean graphs | opus / xhigh | `a54604c9ec4fc8fac` | 0 | merged | `ws/B` | C1 | `Pipeline.lean`, `Components.lean`, `Acyclic.lean` | `lake build`, zero `sorry` |
| D | Data acquisition | sonnet / high | `a896e3b530ce7f2c7` | 0 | merged | `ws/D` | — | `pipeline/env/`, `data/raw/` | `python -c "import opensim"` loads model and trial |
| E | Web scaffold | sonnet / medium | `ac8730c51e9090ac6` | 0 | merged | `ws/E` | C2, C3 | `web/` | `tsc` clean; `npm run build` |
| H | Arch viewer | sonnet / high | `a9e35040ecfdb0d36` | 0 | merged | `ws/H` | C4 | `tools/arch/` | `mypy`; `print --detail 0..3`; `svg`; watch redraw < 2 s |

## Wave 2

| ID | Workstream | Model / effort | Worker ID | Fails | State | Inputs | Acceptance |
|---|---|---|---|---|---|---|---|
| C | Emitters | opus / high | `a0d7098928e70d129` | 0 | merged | A, B | regenerate gives an empty diff; `ninja -n` |
| P1 | Pipeline stages 1–3 | opus / high | `aa1666b96d68aaa97` | 0 | merged | D, C2 | `mypy`; tibialis anterior and gluteus medius plausibility |
| F | Lean checkers | opus / high | `a4950df23482a4305` | 0 | merged | C1, A, C3 | fixture passes; bad edge and bad trace fail by name |
| E2 | ArchitectureView | sonnet / medium | `ab4fb0d019ad1eadf` | 0 | merged | C (`architecture.json`) | `tsc`; four diagrams render |

## Coordinator tasks

| Task | State | Detail |
|---|---|---|
| K1 Add `data/work/forces.csv`, `data/work/static_opt.json` to `runStaticOpt` writes in `Pipeline.lean` | dropped | side outputs with no reader; `read_unless_out` requires a reader for every non-final artefact |
| K2 `supportInterpreter := true` on `lean_exe gen`, then C deletes `runInterpreted` | todo | optional speed-up |
| K3 `data/raw/ontology/` moves from D to P2 | merged | P2 fetches Uberon/FMA subsets |
| K5 Wire ArchitectureView into App at `#/architecture` | merged | `web/src/main.ts`, `web/index.html` |
| K6 App calls `highlightState` from `recorder.onStep` in dev mode | merged | `web/src/main.ts` |
| K13 Wire movement view into App at `#/walking` | merged | `web/src/main.ts`, `web/index.html` |
| K7 Enable the deploy job (D-003) and set `SOURCE_BASE_URL` | merged | live at https://argent0.github.io/bio-mechanics/ |
| K8 Declare missing stage inputs in `Pipeline.lean` (segmentPhases, labelRoles, exportMeshes) | merged | B's worker `a54604c9ec4fc8fac` |
| K9 Commit Uberon subset; ignore ninja state | merged | FMA subset stays local (licence) |
| K10 Import boundaries checked by `tests/test_boundaries.py` from `generated/eslint-boundaries.json` | merged | typescript-eslint supports TypeScript < 6.1; the app uses 7 |
| K11 D-004 activation floor in labelRoles | merged | graph.json 543 edges |
| K12 Investigate low vasti activation in loading response (static optimisation) | merged | no defect in stages 1–3; D-004's whole-phase floor hides the braking; evidence test in `test_p1_stages.py` |
| K14 `exportMusclePaths` reads `phases` (edge `segmentPhases → exportMusclePaths`) | merged | B's worker |
| K4 Set `PIPELINE_TARGET` in `ci.yml` to the full graph | merged | CI pipeline job (then `pipeline-smoke`) green |
| K16 CI `python` job installs `types-PyYAML` | merged | coordinator fix in `ci.yml` (G's file), one package |
| K17 CI compares regenerated graph.json structurally (`scripts/compare_graph.py`) | merged | IK and SO drift across machines; ≤ 5 % of edges may differ, all listed |
| K18 D-006 combined role floor | merged | all teaching tests pass; 550 edges |
| K15 D-005 relative role floor | merged | vasti braking restored; calf mid-stance role lost, adductors back (director question) |

## Wave 3

| ID | Workstream | Model / effort | Worker ID | Fails | State | Inputs | Acceptance |
|---|---|---|---|---|---|---|---|
| P2 | Pipeline stages 4–7 | opus / high | `ab4d531a834c2a987` | 0 | merged | P1, C, D-002 | `ninja`; `lake exe checkGraph data/out/graph.json` |
| E3 | Movement views | sonnet / high | `af7d5ed9f2a5e08a4` | 0 | merged | C, P2 | `tsc`; `tests/test_boundaries.py`; walking plays and scrubs |
| G | CI and traces | sonnet / medium | `a9065076c8beaed8a` | 1 | merged | F, C | CI green on `main` |

## Wave 4 — Integration (coordinator)

| Task | State |
|---|---|
| Replace fixture references with pipeline output | merged (`web/src/config.ts` reads `data/out/graph.json`; Vite serves `data/out/`) |
| Full gate on `main` | merged (local with OpenSim; CI run 40993670056 all six jobs green) |
| Record a walking trace, pass `lake exe conform` | merged (`data/fixtures/trace.walking-session.json`: ui 6, gait 17 + 10 steps; in the gate) |
| Fresh `handover.md` status from merged code | merged |
| Director: order of later movements | deferred by the director (2026-10-29) |

## Escalations

| Workstream | From | To | Reason |
|---|---|---|---|

## Open items for the director

1. Order of later movements (Wave 4).

# Whole body

Source plan: `plan.md` (2026-10-30). The sections above are the first slice, kept as history.

## Wave 0 — Foundation (coordinator, K19 in parallel)

| Task | Owner | Model | State | Inputs | Output | Acceptance |
|---|---|---|---|---|---|---|
| 0.1 Section **Whole body** with every task of `plan.md` | coordinator | opus | merged | `plan.md` | this section | each task has owner, model, state, inputs, outputs, acceptance |
| 0.2 Launch K19 | coordinator | opus | merged | — | K19 running | report in hand before 0.7 |
| 0.3 Q1 phase timeline | coordinator | opus | merged | — | D-007: reference leg | answer before 0.4 |
| 0.4 **C1** `Region`, `NodeAttrs.region`, `Kind.regional_iff`; `checkGraph` needs a region on every regional node (`check_ok_region`) | coordinator | opus | merged | D-007 | `Schema.lean`, `CheckGraph.lean`, schema version 4 | `lake build`, zero `sorry` |
| 0.5 **C2** regenerate | coordinator | opus | merged | C1 | `generated/ts/types.ts`, `generated/py/schema.py` | regenerate gives an empty diff |
| 0.6 **C3** fixture: left knee, lumbar joint, right shoulder and elbow, their muscles; `region` on every node | coordinator | opus | merged | C1 | `graph.sample.json` (50 nodes, 103 edges), `graph.bad-edge.json` | `checkGraph` passes the sample, names `edges[103]` of the bad one |
| 0.6a Regions in the pipeline: `anatomy.yaml` `regions`, `enrich_anatomy.regions_of`; `data/out/graph.json` regenerated (edges unchanged) | coordinator | opus | merged | C1 | `region` on every node of `graph.json` | `checkGraph ../data/out/graph.json`; gate |
| 0.6b `compare_graph.py --within-committed` | coordinator | opus | merged | — | `scripts/compare_graph.py`, `tests/test_compare_graph.py` | pytest |
| 0.7 K19 picks confirmed against D-008 | coordinator | opus | merged | K19 report | picks below | picks before D2 |
| 0.8 Module map: S, L, D2, W1, G2, M, P4, W2; APIs C8, C9 | coordinator | opus | merged | — | `Architecture.lean` | `lake exe arch check` |

| ID | Investigation | Model / effort | Worker ID | State | Output |
|---|---|---|---|---|---|
| K19 | Upper-body model survey (trunk, arm, neck picks) | opus / high | `a61d8613137080615` | merged | ranked table, one pick per region |

K19 picks (each muscle-driven, merged onto Rajagopal bodies: consistent with D-008):

| Region | Pick | Licence | Source | OpenSim 4.6 load |
|---|---|---|---|---|
| Trunk | FBLS, Raabe & Chaudhari 2016 (D-011; replaces the Christophy pick, simtk.org down) | academic, no redistribution: git-ignored | `rocketheat/multifidus_atrophy@15f5de3` | pass (format 40500) |
| Arm | Holzbaur 2005 Stanford-VA upper limb, 50 muscles | BSD-3 (Stanford, VA Palo Alto 2005) | `mitkof6/OpenSimDatabase@0911687…` `upper_limb/complex/Stanford_VA_upper_limb/Stanford_VA_Upper_Limb_original.osim` | pass |
| Neck | Mortensen 2018 HYOID 1.2, 72 muscles | MIT (2018) | `MyoHub/myoconverter@cadf380…` `models/osim/Neck6D/HYOID_1.2_ScaledStrenght_UpdatedInertia.osim` | pass |

Risks for M from K19: lumbar vertebra bodies and couplers (normalised axial coefficients); trunk frame offset and scale; shoulder points and wraps onto `torso` (no scapula body); Holzbaur via-bodies and couplers; wrist coordinates locked in Rajagopal; left arm by mirroring; muscle type to Millard2012; head split (7.72 kg out of `torso`, skull meshes move); Mortensen's two 3-axis neck groups need a split rule for D-010; Mortensen's bushings and extra actuators; clavicle and scapula neck attachments move to `torso`.

## Wave 1

| ID | Workstream | Model / effort | Worker ID | Fails | State | Branch | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|---|---|---|---|
| S | Lean spec additions | opus / xhigh | `a19ea05ec567d708b` | 0 | merged | `ws/S` | C1, D-008 | stage `buildModel` before `loadModel`; component `RegionFilter`; region emitters | acyclicity and layering theorems; zero `sorry`; `ninja -n -f generated/pipeline.ninja` |
| L | Left leg | opus / high | `a3bc0e6b1242c20ea` | 0 | merged | `ws/L` | C1–C3, D-007 | both legs on the reference timeline; left anatomy by mirroring; left meshes, paths, dynamics | 40 left-leg muscles; `compare_graph.py --within-committed` passes; mirrored teaching examples; `checkGraph` |
| D2 | Upper-body data | sonnet / high | `a25da4ada23abbe0a` | 0 | merged (arm 50, neck 72 muscles load; trunk waits on the director's download) | `ws/D2` | D-008, K19 picks | fetch script, `SHA256SUMS`, `SOURCES.md` section | `check_env.py` loads the model in OpenSim 4.6 |
| W1 | Web, whole-body views | sonnet / high | `a208befd13ed6f3b2` | 0 | merged | `ws/W1` | C2, C3 | whole-skeleton framing; region and side filter; panels grouped by region and side; search across regions | `tsc`; web tests; boundary test with `RegionFilter` once S merges |
| G2 | CI | sonnet / medium | `a975d8edca84b9c28` | 0 | merged (CI run on GitHub pending a push) | `ws/G2` | D2 | CI fetches and caches the upper-body model; every stage runs | CI green on `main`; pipeline job under 15 minutes |

| Task | State | Detail |
|---|---|---|
| K20 Pass-through `pipeline/build_model.py`, empty `pipeline/config/model.yaml` (M's paths, before M starts) | merged | ninja needs both; pipeline output byte-identical |
| K21 App wires `RegionFilter` (`web/src/main.ts`, `web/index.html`) | merged | search, GraphView, PhasePanel, DynamicsPanel, Viewer3D share one filter |
| K22 Stage scripts default to `paths.MERGED_MODEL`, `paths.IK_FULL` (the reads ninja declares) | merged (M half); P4: export scripts | M: `load_model.py`, `static_opt.py`, `moment_arms.py`, `segment_phases.py` |
| K23 `buildModel` reads the upper-body model files once D2 fixes their paths | merged | six source artefacts plus `geometry`; `tests/test_merge_recipe.py` keeps `model.yaml` and the reads in sync |
| K28 ninja: each stage also depends on the `pipeline/*.py` modules it imports (per-stage list in `Pipeline.lean`) | running | S worker resumed |
| K26 Static optimisation under 15 min in CI (462 muscles: 24 min locally); CI timeout 60 min meanwhile | running | M: custom convex QP in `static_opt.py` |
| K27 Accept M's commit `c6a1ade` outside its paths: fixtures in `test_p1/p2/l_stages.py`, regions of 15 new bodies in `anatomy.yaml`, `label_roles.py` labels muscles that cross a labelled coordinate | merged | owners L, P2 finished; leg graph unchanged |
| K25 D2: fetch FBLS from its pinned mirror, git-ignored, checksummed (D-011) | merged | 324 muscles load; mirror holds no meshes (vertebra meshes absent); full licence text unobtained (simtk.org down) |
| K24 L's web-test line (ten coordinates in `dynamics.json`); left-aware FMA subset on main | merged | graph 207 nodes, 1096 edges; reproduces on main |

M results: 462 Millard2012 muscles (Rajagopal 80, FBLS 216, Holzbaur 94 on both arms, Mortensen 72); 15 added bodies (`lumbar1..5`, `Abdomen`, `LB_wrap`, `cerv1..7`, `head`); reserve RMS over the stride ≤ 0.031 N·m lumbar, ≤ 0.021 arm, ≤ 0.058 neck; leg activations change ≤ 0.0012 RMS; leg graph 0 of 1096 edges differ. Biceps supination moment arm 0.06 cm against Holzbaur's 0.44 cm (via points frozen at the trial's mean arm pose).

L findings: left vasti brake left knee flexion in reference pre-swing (left loading response); lateral gastrocnemius_l stays under the D-006 floor early in left mid-stance (mean 0.027), while soleus_l and gasmed_l brake. Left foot on a force plate 0.84–1.59 s; left events at 0.45 s and 1.97 s come from markers. Five left entities share a side-neutral FMA id (`mtp`, `gluteals`, `hamstrings`, `deltoid`, `nervePiriformis`).

## Wave 2

| ID | Workstream | Model / effort | Worker ID | Fails | State | Branch | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|---|---|---|---|
| M | Model merge | opus / xhigh | `ac5f4d49260d0cc4a` | 0 | merged | `ws/M` | D2, S, D-008–D-010 | merged model, head split, neck angles holding the head level, reserves | static optimisation over the stride; reserves RMS < 10 N·m lumbar, < 2 N·m arm, < 1 N·m neck; leg activations within 0.02 RMS of today |
| P4 | Trunk and arm stages | opus / high | `a749e226a23d368b2` | 0 | running | `ws/P4` | M, L, D-009 | roles for neck, lumbar, shoulder, elbow, forearm, wrist; curated anatomy; meshes | erector spinae two bursts per stride; posterior deltoid in backward swing; neck extensors stabilising; D-006 floor test; `checkGraph` |
| W2 | Web, real output | sonnet / medium | — | 0 | todo | `ws/W2` | P4, S | real graph wired in; tubes for every muscle | ≥ 30 fps with every muscle; `data/out/` < 8 MB; recorded trace conforms |

## Wave 3 — Integration (coordinator)

| Task | State |
|---|---|
| Fixture references replaced by real output; full gate on `main` | todo |
| Whole-body walking trace; `lake exe conform` | todo |
| `README.md` pointers, `handover.md` | todo |
| Deploy; `#/walking` shows both legs, trunk and arms | todo |

## Escalations (whole body)

| Workstream | From | To | Reason |
|---|---|---|---|
