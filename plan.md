# Plan: Implementing the Handover with Parallel Agents

Status as of 2026-10-29. Source document: `handover.md`. This plan splits the handover's ten next steps into workstreams that run in parallel, with one coordinator agent that owns the order, the contracts, and the merges.

## Jargon

| Term | Meaning |
|---|---|
| **Coordinator** | The agent that owns the task board, assigns workstreams, merges finished work, and brings open items to the director. |
| **Worker** | An agent assigned one workstream. It works in its own git worktree and hands back a branch. |
| **Workstream** | A sequence of tasks with one owner and one directory of responsibility (e.g. `spec/BioMech/GaitFsm.lean`). |
| **Wave** | A group of workstreams that run at the same time. A wave starts once its inputs are merged on `main`. |
| **Contract** | A file that several workstreams read and one workstream writes, e.g. `Schema.lean` or `graph.json`'s shape. Contracts freeze before the wave that reads them. |
| **Fixture** | A small hand-made sample of a contract's output (e.g. `data/fixtures/graph.sample.json`) that lets readers start before the writer finishes. |
| **Worktree** | A separate checkout of the same git repository (`git worktree`), so workers edit files side by side safely. |
| **Task board** | `TASKS.md` at the repository root: every task with its owner, model, worker ID, failure count, state, inputs, and outputs. The coordinator is its sole writer. |
| **Worker ID** | The agent ID the `Agent` tool returns at launch. `SendMessage` to this ID resumes the same worker with its full context. |
| **Module map** | `spec/BioMech/Architecture.lean`: every module (one per workstream, with its owned paths), every API between modules (the contracts), and which module generates and which consumes each API. The single source for ownership. |
| **Arch tool** | `lake exe arch`: `check` (every file owned by exactly one module), `export` (writes `generated/modules.json`), `print --detail N` (the map as text). The viewer `tools/arch/` adds `watch` (live terminal map) and `svg`. |
| **Gate** | A check a branch passes before merge: `lake build`, `lake exe gen` with an empty diff, `tsc`, `mypy`, `lake exe arch check`, `lake exe arch print --detail 0`, plus the workstream's own acceptance test. |
| **Green main** | `main` passing the full gate at every commit. |
| **Model tier** | The Claude model an agent runs on. From most to least capable: Fable 5.1 (`fable`), Opus 5.5 (`opus`), Sonnet 5.5 (`sonnet`), Haiku 5.5 (`haiku`). Price per million output tokens: $50, $20, $10, $0.50. |
| **Effort** | How deeply an agent reasons per step: `low`, `medium`, `high`, `xhigh`, `max`. Higher effort spends more tokens for more careful work. |
| **Escalation** | Relaunching a stuck workstream on the next tier up, with the previous attempt's report as input. |

## Principles

1. **Contracts first.** Everything downstream reads `Schema.lean` and the generated types, so the coordinator lands those on `main` before any wave fans out.
2. **One owner per file.** Each workstream owns its directories. Shared files (contracts, `TASKS.md`, `lakefile.lean`, root config) belong to the coordinator.
3. **Fixtures unblock readers.** Web and checker work starts on fixtures; the real pipeline output replaces them in a later wave.
4. **Source code is the truth.** Workers carry facts in code and code comments; documentation is generated from them (`CLAUDE.md`).
5. **Director decisions arrive one question at a time**, asked by the coordinator at the moment a workstream needs the answer.
6. **The architecture is visible at all times.** From Wave 0 on, every commit on `main` holds a module map that `lake exe arch print` draws. Each workstream is a module, its owned paths are the module's paths, and each contract is an API. Generators sit above their consumers. Zoom levels: 0 names and arrows, 1 boxed modules with API names, 2 a head line per box (language, owner, state), 3 everything (paths, acceptance commands, API files).
7. **Green main.** A new gate check lands in the same commit as the data or code that satisfies it, or with a recorded exemption.
8. **Acceptance criteria are hard numbers and exact commands**, e.g. "between 20 and 25 nodes", "zero `sorry`".

## Roles

### Coordinator (one agent, runs for the whole project)

- Runs Wave 0 personally.
- Writes and maintains `TASKS.md`.
- Creates each worker's worktree and branch itself (`git worktree add ../bm-<ID> -b ws/<ID>`) and puts the absolute worktree path in the brief. `isolation: "worktree"` becomes an option once a toy run inside this repository confirms where the harness places the worktree and which branch it starts from.
- Launches workers with a brief naming its worktree path, owned paths, input contracts, outputs, acceptance test, and the gate steps that belong to other owners.
- Records each worker ID in `TASKS.md`.
- Before launching a workstream, adds its module to the module map and commits it on `main`, so the map shows the module before its code exists.
- Reviews each returned branch: `git diff --name-only main...<branch>` lists only owned paths, and the gate passes in the worktree. Then it merges to `main`, regenerates `generated/`, and reruns the gate on `main`.
- Changes a frozen contract only through a coordinator task, then re-briefs every affected worker.
- Keeps the open items list and asks the director exactly one question at a time, when that answer is the next thing blocking work.
- Keeps the wave size at five workers or fewer.

### Workers (one agent per workstream)

- First report `pwd`, `git rev-parse --show-toplevel`, and `git branch --show-current`.
- Work only inside their owned paths, inside their worktree.
- Read contracts; propose contract changes to the coordinator in their report.
- Finish with a report: branch name, what passes, what remains, and any proposed contract change.

## Model selection

Rule: the tier follows the hardest kind of reasoning in the task. Formal proofs, contract design, and biomechanics correctness go to Opus 5.5. Conventional application code and tooling go to Sonnet 5.5. Read-only lookups and log triage go to Haiku 5.5. Fable 5.1 is the escalation tier, used when an Opus 5.5 worker stays stuck after two gate rounds.

| Agent | Model | Effort | Reason |
|---|---|---|---|
| Coordinator (incl. Wave 0, Wave 4) | `opus` | `high` | Designs contracts C1–C3, reviews every branch, and holds the whole project in mind; it runs for the whole project, so Opus 5.5 keeps that long run affordable. |
| **A** Lean FSMs | `opus` | `xhigh` | Lean proofs over DFAs; correctness rests on theorem statements and proof search. |
| **B** Lean graphs | `opus` | `xhigh` | Acyclicity and layering proofs by `decide`; needs care in keeping types small (see Risks). |
| **C** Emitters | `opus` | `high` | Lean metaprogramming that every generated file depends on. |
| **F** Lean checkers | `opus` | `high` | Lean executables whose error messages name the failing edge or trace step. |
| **P1** Pipeline stages 1–3 | `opus` | `high` | OpenSim static optimisation and moment arms; physiological plausibility needs domain judgment. |
| **P2** Pipeline stages 4–7 | `opus` | `high` | Gait-phase segmentation and muscle-role labels define the facts the app teaches. |
| **D** Data acquisition | `sonnet` | `high` | Installs, downloads, and licence notes; well-trodden steps with occasional install debugging. |
| **E** Web scaffold | `sonnet` | `medium` | Standard Vite + TypeScript setup over a fixed fixture. |
| **E2** ArchitectureView | `sonnet` | `medium` | Renders diagrams from a given `architecture.json`. |
| **E3** Movement views | `sonnet` | `high` | Larger Three.js and timeline work, still conventional front-end code. |
| **G** CI and traces | `sonnet` | `medium` | GitHub Actions workflows and a trace recorder. |
| **H** Arch viewer | `sonnet` | `high` | Layered layout and a terminal UI over `generated/modules.json`; conventional code with a clear input. |
| Lookups and gate-log triage (`Explore` agents) | `haiku` | `low` | Searching files, summarising long `lake build` or CI logs for the coordinator. |
| Escalation of any Lean or pipeline workstream | `fable` | `high` | Most capable tier, for proofs or numerics that resist two Opus 5.5 rounds. |

The coordinator passes `model` and `effort` from this table on every `Agent` call. A Haiku 5.5 or Sonnet 5.5 worker that fails its gate twice escalates one tier up; an Opus 5.5 worker escalates to Fable 5.1. The coordinator records each escalation in `TASKS.md`: from-tier, to-tier, reason.

Escalation brief: the previous worker's report, every failing gate output, the same worktree and branch, and the owned paths restated. The new worker reviews the commits already on its branch and builds on them.

Two toy runs on 2026-10-29 confirmed this way of working with a Sonnet 5.5 coordinator and Haiku 5.5 and Sonnet 5.5 workers: parallel worktrees, owned paths, fixtures, gate, merges, `SendMessage` resume, and escalation all worked.

## Waves

### Wave 0 — Foundation (coordinator, serial)

Handover steps 1, 2 (schema part), 4 (first emitter).

| Task | Output | Acceptance |
|---|---|---|
| 0.1 `git init` in the project root, layout from handover, `.gitignore`, `TASKS.md`, one baseline test so the gate's test run counts at least one test | repository skeleton | tree matches handover layout; gate passes |
| 0.2 Lean package with Mathlib pinned to Mathlib's toolchain; `lake exe cache get` | `spec/lakefile.lean`, `spec/lean-toolchain` | `lake build` succeeds |
| 0.3 `Schema.lean`: `Kind`, `SchemaArrow`, `Quiver` instance, attribute structures | **contract C1** | `lake build` succeeds |
| 0.3a Module map `Architecture.lean` with modules A–H plus `coordinator`, the APIs C1–C4, and `lake exe arch check / export / print` | **contract C4** (`generated/modules.json`) | `arch check` passes; `arch print --detail 1` draws every module and API |
| 0.4 Minimal `lake exe gen` emitting `types.ts` and `schema.py` from C1, with the header line | **contract C2** (`generated/ts/types.ts`, `generated/py/schema.py`) | regenerate gives an empty diff |
| 0.5 Hand-written fixture `data/fixtures/graph.sample.json` (20 to 25 nodes around the knee and hip) typed against C2 | **contract C3** (graph.json shape) | validates against `schema.py`; node count between 20 and 25 |
| 0.6 Ask the director: initial contact as its own DFA state, or an instant at the start of loading response | decision recorded in `DECISIONS.md` | answer in hand before Wave 1 workstream A starts |

### Wave 1 — Five parallel workstreams

| ID | Workstream | Owned paths | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|
| **A** | Lean FSMs (handover step 2) | `spec/BioMech/GaitFsm.lean`, `UiFsm.lean` | C1, decision 0.6 | gait DFA and UI DFA with `Fintype`, `DecidableEq`, decidable `accept`; theorems: one-stride word returns to start, every phase reached, every UI state reaches `idle`, `scrubbing` ends in `paused` | `lake build` with zero `sorry` |
| **B** | Lean graphs (handover step 3) | `spec/BioMech/Pipeline.lean`, `Components.lean`, `Acyclic.lean` | C1 | stage and component Digraphs; acyclicity by `decide`; topological order; layering theorem `Viewer3D` → `GraphStore` only via `QueryEngine` | `lake build` with zero `sorry` |
| **D** | Data acquisition (handover step 5) | `data/raw/`, `pipeline/env/` | — | OpenSim Python bindings installed (conda env file), Rajagopal model + walking trial in `data/raw/`, licence notes for SimTK, Uberon, FMA | `python -c "import opensim"` loads the model and trial |
| **E** | Web scaffold (handover step 8, start) | `web/` | C2, C3 | Vite + TypeScript + Three.js + Cytoscape.js app; `GraphStore` and `QueryEngine` over the fixture; `GraphView` showing the fixture | `tsc` clean; `npm run build` produces a static site |
| **H** | Arch viewer (inspired by `dashboardpp`) | `tools/arch/` | C4 | Python viewer: `watch` (terminal map, scroll, zoom 0–3, Tab selects a box and lights its APIs, reloads within 1 s of a change to `generated/modules.json`), `print`, `svg -o FILE` | `mypy` clean; `print --detail 0..3` and `svg` succeed on `main`'s map; a test edits the map and `watch` redraws within 2 s |

### Wave 2 — Four parallel workstreams

Starts once A and B are merged (C) and D is merged (P1).

| ID | Workstream | Owned paths | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|
| **C** | Emitters (handover step 4, rest) | `spec/BioMech/Gen/` | A, B | `gaitFsm.ts`, `gait_fsm.py`, `uiFsm.ts`, `pipeline.ninja`, `eslint-boundaries.json`, `architecture.json`, Mermaid and DOT diagrams | regenerate gives an empty diff; `ninja -n` accepts `pipeline.ninja` |
| **P1** | Pipeline stages 1–3 (handover step 6) | `pipeline/load_model.py`, `static_opt.py`, `moment_arms.py` | D, C2 | activations, moment arms, muscle-tendon lengths and velocities per frame | `mypy` clean; plausibility test: tibialis anterior active after initial contact, gluteus medius active in single-leg stance |
| **F** | Lean checkers (handover steps 7, 9 Lean side) | `spec/BioMech/CheckGraph.lean`, `Conform.lean` | C1, A, C3 | `lake exe checkGraph` and `lake exe conform` | fixture passes; a fixture with a bad edge fails with that edge named; a bad trace fails |
| **E2** | Web, ArchitectureView (handover step 8) | `web/src/architecture/` | C's `architecture.json` (fixture copy until C merges) | `/architecture` page rendering schema quiver, both FSMs, pipeline DAG, component DAG, linked to Lean source | `tsc` clean; page renders all four diagrams |

Director question for this wave (asked when P2 approaches): role-classification thresholds.

### Wave 3 — Three parallel workstreams

| ID | Workstream | Owned paths | Inputs | Outputs | Acceptance |
|---|---|---|---|---|---|
| **P2** | Pipeline stages 4–7 (handover step 7) | `pipeline/segment_phases.py`, `label_roles.py`, `enrich_anatomy.py`, `export_*.py`, `pipeline/config/roles.yaml`, `data/curated/*.yaml` | P1, C (`gait_fsm.py`, `pipeline.ninja`), thresholds decision | `data/out/graph.json`, bone glTF, muscle paths per frame | `ninja` runs end to end; `lake exe checkGraph data/out/graph.json` passes |
| **E3** | Web, movement views (handover step 8) | `web/src/viewer/`, `timeline/`, `phase/` | C (`gaitFsm.ts`, `uiFsm.ts`, `eslint-boundaries.json`), P2 output (fixture until merged) | `Viewer3D` with tube muscles coloured by activation and hue by concentric/eccentric; scrubbable `Timeline`; `PhasePanel` with common and anatomical names and roles | `tsc` and eslint boundaries clean; walking plays and scrubs |
| **G** | CI and trace recording (handover steps 9, 10) | `.github/workflows/`, `web/src/trace/` | F, C | dev-mode trace recording to `trace.json`; CI: Lean build, theorems, regenerate-and-diff, `tsc`, `mypy`, pipeline smoke test, `conform` on a recorded trace | CI green on `main` |

Director question for this wave (asked when G reaches deployment): hosting target.

### Wave 4 — Integration (coordinator)

- Replace every fixture reference with real pipeline output.
- Run the full gate on `main`.
- Record a walking session trace in dev mode and pass `lake exe conform`.
- Write a fresh `handover.md` status section from the merged code.
- Ask the director the last open item: order of later movements.

## Dependency graph

```
Wave 0 (coordinator): C1 Schema → C2 types → C3 fixture
                         │
   ┌────────────┬────────┴─────┬──────────────┬──────────────┐
   A FSMs       B Graphs       D Data         E Web scaffold H Arch viewer
   └─────┬──────┘              │              │
         C Emitters ──┐        P1 Stages 1–3  E2 ArchitectureView
         F Checkers   │        │
                      ├────────┴──┐
                      P2 Stages 4–7   E3 Movement views   G CI + traces
                                  └──────────┬──────────┘
                                   Wave 4 Integration
```

## Coordinator brief

The director starts the coordinator session on Opus 5.5 (`claude --model opus`, effort `high`) with this prompt, and keeps the map open beside it with `lake exe arch print` (and `python -m tools.arch watch` once H merges):

> You are the coordinator for the Bio-Mechanics Explorer. Read `CLAUDE.md`, `handover.md`, and `plan.md` in `/home/aner/software/bio-mechanics`. Follow `plan.md`.
>
> 1. Run Wave 0 yourself. Create `TASKS.md` with every task from `plan.md`, each with owner, state (`todo` / `running` / `review` / `merged`), inputs, outputs, and acceptance test. You are its sole writer.
> 2. For each wave: add each workstream's module to the module map and commit it on `main`; create each worktree (`git worktree add ../bm-<ID> -b ws/<ID>`); then launch the workers together in one message, each with the `model` and `effort` that the Model selection table gives its workstream. Record each worker ID in `TASKS.md`. Each brief states: the absolute worktree path, owned paths, input contracts with their paths on `main`, expected outputs, acceptance test with hard numbers, the gate steps owned by others, and the rules "first report `pwd`, repository root, and branch; work only inside your owned paths; report proposed contract changes to the coordinator".
> 3. When a worker returns, check `git diff --name-only main...<branch>` against its owned paths and run the gate in its worktree. Passing branches merge to `main`; then run `lake exe gen`, rerun the gate on `main`, and commit. A failing branch goes back to the same worker ID via `SendMessage` with the exact failing output, and its failure count in `TASKS.md` goes up by one. At two failures, escalate one tier up with the escalation brief from the Model selection section.
> 3a. A new gate check lands in the same commit as its fix or with a recorded exemption, so `main` stays green.
> 4. Start a later-wave workstream as soon as its own inputs are merged; a whole wave finishing first is optional.
> 5. Ask the director one question at a time, only when the answer blocks the next task. Record each answer with the `decision` skill in `DECISIONS.md`.
> 6. After each merge, post a two-line status to the director: what merged, what runs now.
> 7. Commit with the `commit` skill.

## Risks and responses

| Risk | Response |
|---|---|
| Mathlib build time slows every worker | Coordinator runs `lake exe cache get` once in Wave 0; worktrees share `~/.cache/mathlib`. |
| OpenSim install fails through conda | Workstream D records the working install path in `pipeline/env/`; P1 starts only after D's acceptance test passes. |
| A contract change during a wave | Coordinator owns the change as its own task, regenerates, and re-briefs affected workers. |
| Walking trial lacks ground-contact data for event detection | P2 derives events from kinematics (foot marker velocity) and records the method in code comments. |
| Proofs by `decide` time out | Workstream B keeps stage and module types small and finite, and splits lemmas per edge. |
| A Lean workstream stays stuck on Opus 5.5 | Coordinator escalates it to Fable 5.1 with the failing goals and the previous report. |
| Token spend grows with the wave count | Front-end, CI, and data work run on Sonnet 5.5; lookups run on Haiku 5.5; Fable 5.1 runs only on escalation. |
