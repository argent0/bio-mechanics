# Handover: Bio-Mechanics Explorer

Open work only. The code holds everything built so far; `README.md` points into it.

## Jargon

| Term | Meaning |
|---|---|
| **Static optimisation** | The OpenSim tool that estimates each muscle's activation per frame by minimising total activation. |
| **Co-contraction** | Muscles on both sides of a joint active at once, e.g. quadriceps and hamstrings in early stance. |
| **EMG** | Electromyography: measured electrical muscle activity, here recorded with the walking trial. |

## Next steps

1. Later movements (squat, plié, relevé, jump): a trial per movement through the same pipeline, a movement node per trial. The order is deferred by the director (`TASKS.md`).
2. Stretch and strengthen exercise links per muscle, as extra graph edges.
3. Sculpted muscle meshes (Z-Anatomy / BodyParts3D, CC-BY-SA) as a visual upgrade over the tubes.
4. Optional: EMG-informed optimisation, so early stance shows co-contraction (K12, proposal 4).
5. Optional: `supportInterpreter := true` on `lean_exe gen` (K2), and a dagre layout for the architecture diagrams.

## Known limits

- One subject, one trial. The left foot stands on a force plate from 0.84 s to 1.59 s; the left toe-off at 0.45 s and the left initial contact at 1.97 s come from markers (`pipeline/label_roles.py`).
- The graph covers both lower limbs and the pelvis; trunk, arms and neck follow with the model merge (`plan.md`, `TASKS.md` Whole body).
- Solver drift across machines changes a small share of edges (`scripts/compare_graph.py` sets the tolerance). Three roles sit within 10 % of a threshold: gluteus maximus 1 as a mid-stance stabiliser of hip abduction, and gluteus medius 1 and semitendinosus near the helper share in loading-response hip extension.
- Some anatomy entities have no Uberon or FMA identifier.
