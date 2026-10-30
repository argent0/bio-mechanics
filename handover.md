# Handover: Bio-Mechanics Explorer

Open work only. The code holds everything built so far; `README.md` points into it.

## Jargon

| Term | Meaning |
|---|---|
| **Static optimisation** | The OpenSim tool that estimates each muscle's activation per frame by minimising total activation. |
| **Co-contraction** | Muscles on both sides of a joint active at once, e.g. quadriceps and hamstrings in early stance. |
| **EMG** | Electromyography: measured electrical muscle activity, here recorded with the walking trial. |
| **FBLS** | The full-body lumbar spine model of Raabe & Chaudhari (2016), source of the trunk muscles (D-011). |
| **Draw call** | One batch of geometry the GPU renders; the viewer draws muscle tubes in one call per region and side. |

## Next steps

1. Later movements (squat, plié, relevé, jump): a trial per movement through the same pipeline, a movement node per trial. The order is deferred by the director (`TASKS.md`).
2. Stretch and strengthen exercise links per muscle, as extra graph edges.
3. Sculpted muscle meshes (Z-Anatomy / BodyParts3D, CC-BY-SA) as a visual upgrade over the tubes.
4. Optional: EMG-informed optimisation, so early stance shows co-contraction (K12, proposal 4).
5. Optional: `supportInterpreter := true` on `lean_exe gen` (K2), and a dagre layout for the architecture diagrams.
6. Cervical vertebra meshes from Mortensen's `Geometry/` on `cerv1..7` (K31).
7. `computeMomentArms` over frames in parallel; it is the slowest stage now (K33).
8. Ninja tracks the generated `gait_fsm.py` and `schema.py` the stages import (K29).
9. Bone meshes merged per body if the viewer runs under 30 fps (93 bone draw calls).

## Known limits

- One subject, one trial. The left foot stands on a force plate from 0.84 s to 1.59 s; the left toe-off at 0.45 s and the left initial contact at 1.97 s come from markers (`pipeline/label_roles.py`).
- The graph covers the whole body: 462 muscles in five regions, both sides.
- Neck angles rest on an assumption (D-010): the trial's markers stop at the shoulders, so the head is held level in space; the app labels neck roles with it.
- The FBLS trunk model stays out of git (D-011); its full licence text is unobtained while simtk.org is down, and its lumbar vertebrae carry no meshes.
- Arm muscle via points are frozen at the trial's mean arm pose; the biceps' forearm-rotation lever is under 2 mm, so the supinator alone supinates.
- 39 of 94 arm muscles stay under the D-006 floor in every phase: arm swing in walking is largely passive.
- The 30 fps target is measured in headless software rendering only (9–13 fps there); the dev-mode readout in `#/walking` gives the figure on a GPU.
- Solver drift across machines changes a small share of edges (`scripts/compare_graph.py` sets the tolerance). Roles near a threshold include gluteus maximus 1 as a mid-stance stabiliser of hip abduction, gluteus medius 1 and semitendinosus near the helper share in loading-response hip extension, the left medial gastrocnemius on the D-006 floor in left mid-stance, and splenius capitis as a pre-swing neck stabiliser (0.1055 against 0.10).
- Some anatomy entities have no Uberon or FMA identifier.
