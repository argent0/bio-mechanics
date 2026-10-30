"""Workstream P4 acceptance: roles and anatomy of the trunk, arms and neck on the merged model.

Static optimisation on the merged model (462 muscles) takes about 24 minutes, so these tests
read the outputs the pipeline wrote (`ninja -f generated/pipeline.ninja`: `data/work/` and
`data/out/`) and skip when they come from another model. Every phase a test reads is found from
the data: the reference stride's events (`roles.json` `events`), the coordinate's change over a
phase, or the frames where an activation curve or a joint angle does what the test names.

Teaching examples pinned here, with the numbers this trial gives:
  - Erector spinae (iliocostalis and longissimus of the trunk, force-weighted mean activation
    per side) above the D-006 floor `roleMinActivation` (0.015) in two bursts per stride, each
    within 10 % of the stride of one initial contact (`test_erector_spinae_...`).
  - Posterior deltoid: its stride peak falls in the arm's backward swing, where it is a
    concentric main mover of shoulder extension.
  - Neck extensors: the lower neck holds still (under 5 degrees) with an extensor moment in all
    seven phases, and splenius capitis stabilises it in pre-swing.
  - D-006 floor: `ARM_BELOW_FLOOR`, the arm muscles inactive in every phase (arm swing is largely
    passive in walking).
  - Biceps: its forearm-rotation moment arm stays under the 5 mm floor, so it takes no
    pronation or supination role; its elbow roles are pinned per phase.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import schema
from pipeline import export_meshes, label_roles
from pipeline.load_model import REPO, Table, read_csv

import pipeline_paths as paths

WORK = REPO / "data" / "work"
OUT = REPO / "data" / "out"
OUT_LIMIT_BYTES = 8_000_000
INITIAL_CONTACT_WINDOW_PCT = 10.0
ARM_GROUPS = ("scapulohumeral", "pectoralisMajor", "anteriorArm", "posteriorArm", "anteriorForearm", "posteriorForearm")
"""Muscle groups that together hold every Holzbaur arm muscle of a side."""

ARM_BELOW_FLOOR = {
    f"{m}_{s}"
    for s in "rl"
    for m in (
        "PECM1", "PECM2", "PECM3", "CORB", "TRIlat", "TRImed", "ANC", "ECRB", "PT", "PQ",
        "FDSL", "EDCL", "EDCR", "EDCM", "EDCI", "EDM", "EIP", "EPL", "EPB",
    )
} | {"TMIN_r"}
"""Arm muscles whose phase-mean activation stays under the D-006 floor in all seven phases: 19
on each side, and the right teres minor (the left one helps internal rotation in loading
response)."""


class Run:
    def __init__(self) -> None:
        self.roles: dict[str, Any] = json.loads((WORK / "roles.json").read_text())
        self.enriched: dict[str, Any] = json.loads((WORK / "enriched.json").read_text())
        self.model: dict[str, Any] = json.loads((WORK / "model.json").read_text())
        self.graph: dict[str, Any] = json.loads((OUT / "graph.json").read_text())
        self.meshes: dict[str, Any] = json.loads((OUT / "meshes" / "index.json").read_text())
        self.paths: dict[str, Any] = json.loads((OUT / "muscle_paths.json").read_text())
        self.dynamics: dict[str, Any] = json.loads((OUT / "dynamics.json").read_text())
        self.act: Table = read_csv(WORK / "activations.csv")
        self.kin: Table = read_csv(WORK / "kinematics.csv")
        self.force = {m["name"]: float(m["maxIsometricForce"]) for m in self.model["muscles"]}
        s = self.roles["stride"]
        self.s0, self.s1 = float(s["start"]), float(s["end"])
        self.frames = [i for i, t in enumerate(self.act.time) if self.s0 - 1e-9 <= t <= self.s1 + 1e-9]

    def pct(self, t: float) -> float:
        return 100.0 * (t - self.s0) / (self.s1 - self.s0)

    def event_pct(self, event: str) -> float:
        return self.pct(next(e["time"] for e in self.roles["events"] if e["event"] == event))

    def action(self, phase: str, coordinate: str) -> dict[str, Any]:
        ph = next(p for p in self.roles["phases"] if p["phase"] == phase)
        return next(a for a in ph["actions"] if a["coordinate"] == coordinate)

    def roles_of(self, muscle: str, coordinate: str) -> dict[str, tuple[int, str, str]]:
        """phase -> (direction, role, contraction) of `muscle` about `coordinate`."""
        out = {}
        for p in self.roles["phases"]:
            a = self.action(p["phase"], coordinate)
            for m in a["muscles"]:
                if m["muscle"] == muscle:
                    out[p["phase"]] = (a["direction"], m["role"], m["contraction"])
        return out

    def weighted(self, muscles: Sequence[str]) -> list[float]:
        """Force-weighted mean activation Σ a·F / Σ F over the stride's frames."""
        total = sum(self.force[m] for m in muscles)
        return [sum(self.act.columns[m][i] * self.force[m] for m in muscles) / total for i in self.frames]


@pytest.fixture(scope="module")
def run() -> Run:
    f = WORK / "static_opt.json"
    if not f.exists() or json.loads(f.read_text())["model"] != paths.MERGED_MODEL:
        pytest.skip("data/work/ comes from the pipeline on the merged model (ninja)")
    r = Run()
    if "lumbar_extension" not in r.roles["coordinates"]:
        pytest.skip("data/work/roles.json comes from the whole-body roles.yaml")
    return r


def bursts(on: Sequence[bool]) -> list[tuple[int, int]]:
    """Maximal runs of `on` as (first, last) indices over a cyclic stride whose last frame is
    the next stride's first; a run through the stride's end continues at its start, so `last`
    may exceed len(on) - 1."""
    runs: list[list[int]] = []
    for k, o in enumerate(on):
        if o and runs and runs[-1][1] == k - 1:
            runs[-1][1] = k
        elif o:
            runs.append([k, k])
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == len(on) - 1:
        runs = [[runs[-1][0], runs[0][1] + len(on) - 1]] + runs[1:-1]
    return [(a, b) for a, b in runs]


def cyclic_gap(pct: float, lo: float, hi: float) -> float:
    """Distance in percent of the stride from `pct` to the interval [lo, hi] (hi may exceed 100)."""
    return min(max(0.0, lo - p, p - hi) for p in (pct, pct + 100.0, pct - 100.0))


# ---------------------------------------------------------------------------------------------
# Graph, anatomy and outputs.


def test_graph_holds_the_whole_body(run: Run) -> None:
    g = run.graph
    assert schema.validate_graph(g) == []
    muscles = Counter((n["region"], n["side"]) for n in g["nodes"] if n["kind"] == "muscle")
    assert muscles == {
        ("lowerLimb", "right"): 40, ("lowerLimb", "left"): 40,
        ("pelvis", "right"): 6, ("pelvis", "left"): 6,  # external obliques, inserting on the pelvis
        ("trunk", "right"): 94, ("trunk", "left"): 94,
        ("upperLimb", "right"): 61, ("upperLimb", "left"): 61,  # 47 Holzbaur and 14 latissimus dorsi
        ("head", "right"): 30, ("head", "left"): 30,
    }
    assert sum(muscles.values()) == len(run.model["muscles"]) == 462
    # Nodes hold exactly; solver drift across machines flips a few `drivenBy` edges at role
    # thresholds (5013 here, 5014 on the CI runner), so edges hold within 1 %.
    assert len(g["nodes"]) == 827
    assert abs(len(g["edges"]) - 5013) <= 50
    ids = {n["id"] for n in g["nodes"]}
    for i in ("joint:lumbarSpine", "joint:cervicalSpine", "joint:craniovertebral", "joint:shoulder_l", "joint:wrist_r",
              "bone:skull", "bone:l3", "bone:atlas", "action:neck_extension", "action:forearm_supination_l",
              "group:erectorSpinae_r", "nerve:accessory_l", "ligament:nuchal"):
        assert i in ids, i


def test_left_upper_body_mirrors_the_right(run: Run) -> None:
    nodes = {n["id"]: n for n in run.graph["nodes"]}
    left = [i for i, n in nodes.items() if n["side"] == "left"]
    assert len(left) == len([n for n in nodes.values() if n["side"] == "right"])
    for i in left:
        r = nodes[i[:-2] + "_r"]
        assert (nodes[i]["kind"], nodes[i]["name"], nodes[i]["region"], nodes[i]["uberonId"]) == (r["kind"], r["name"], r["region"], r["uberonId"]), i


def test_regions_of_the_added_bodies(run: Run) -> None:
    """The regions M gave the added bodies (anatomy.yaml `regions`), confirmed: the lumbar
    vertebrae and FBLS's wrapping bodies in the trunk, the cervical vertebrae with the head."""
    b = run.enriched["entities"]["bone"]
    assert {b[k]["region"] for k in ("l1", "l2", "l3", "l4", "l5", "thoracicSpine", "ribCage", "clavicle_r", "scapula_l")} == {"trunk"}
    assert {b[k]["region"] for k in ("atlas", "axis", "c3", "c7", "skull", "mandible", "hyoid")} == {"head"}
    j = run.enriched["entities"]["joint"]
    assert (j["lumbarSpine"]["region"], j["cervicalSpine"]["region"], j["shoulder_r"]["region"]) == ("trunk", "head", "upperLimb")


def test_meshes_cover_torso_head_arms_and_hands(run: Run) -> None:
    idx = run.meshes
    bodies = [b["body"] for b in idx["bodies"]]
    assert {"torso", "head", "humerus_r", "ulna_l", "radius_r", "hand_l"} <= set(bodies) and len(bodies) == 23
    assert [u["body"] for u in idx["unmeshed"]] == [f"lumbar{i}" for i in range(5, 0, -1)] + ["Abdomen", "LB_wrap"] + [f"cerv{i}" for i in range(7, 0, -1)]
    assert {u["body"] for u in idx["unmeshed"]} == set(export_meshes.UNMESHED)
    head = next(b for b in idx["bodies"] if b["body"] == "head")
    assert [m["file"] for m in head["meshes"]] == ["hat_jaw.vtp", "hat_skull.vtp"]  # moved from the torso (D-009)
    for b in idx["bodies"]:
        assert (OUT / "meshes" / b["file"]).exists() and b["triangles"] > 0


def test_muscle_paths_draw_every_muscle_and_pose_every_body(run: Run) -> None:
    p = run.paths
    assert set(p["muscles"]) == {m["name"] for m in run.model["muscles"]}
    assert set(p["bodies"]) == {b["name"] for b in run.model["bodies"]}
    assert p["rateHz"] == 25.0 and p["time"] == run.dynamics["time"]
    for m, v in p["muscles"].items():
        assert len(v["points"]) == len(p["time"]) and all(len(x) >= 6 and len(x) % 3 == 0 for x in v["points"]), m


def test_dynamics_cover_every_labelled_coordinate(run: Run) -> None:
    d = run.dynamics
    assert [c["coordinate"] for c in d["coordinates"]] == run.roles["coordinates"]
    lumbar = next(c for c in d["coordinates"] if c["coordinate"] == "lumbar_extension")
    assert lumbar["joint"] == "joint:lumbarSpine" and {m[-2:] for m in lumbar["moments"]} == {"_r", "_l"}


def test_out_stays_under_8_mb(run: Run) -> None:
    sizes = {str(f.relative_to(OUT)): f.stat().st_size for f in OUT.rglob("*") if f.is_file()}
    assert sum(sizes.values()) < OUT_LIMIT_BYTES, sorted(sizes.items(), key=lambda x: -x[1])[:5]


# ---------------------------------------------------------------------------------------------
# Teaching examples.


def test_erector_spinae_burst_around_each_initial_contact(run: Run) -> None:
    """Each side's trunk erector spinae rise above the D-006 floor in two bursts per stride, one
    within 10 % of the stride of each initial contact. This trial (force-weighted mean, % of the
    stride): right 94-17 % (peak 0.083 at 7 %) and 58-72 % (peak 0.066 at 63 %); left 2-22 %
    (peak 0.105 at 15 %) and 45-50 % (peak 0.024 at 48 %). Right initial contact at 0 %, left at
    49.6 %. The bursts peak after the contacts, in each loading response."""
    floor = run.roles["config"]["roleMinActivation"]
    contacts = [0.0, run.event_pct("oppositeInitialContact")]
    pct = [run.pct(run.act.time[i]) for i in run.frames]
    peaks: dict[str, list[float]] = {}
    for side in "rl":
        es = [m for m, a in run.enriched["muscles"].items() if f"erectorSpinae_{side}" in a["groups"] and run.enriched["entities"]["muscle"][m]["region"] == "trunk"]
        assert len(es) == 38  # 12 iliocostalis and 26 longissimus fascicles
        curve = run.weighted(es)
        runs = bursts([c >= floor for c in curve])
        assert len(runs) == 2, (side, runs)
        n = len(curve) - 1
        spans = [(pct[a % n], pct[b % n] + (100.0 if b >= n else 0.0)) for a, b in runs]
        near = [[cyclic_gap(ic, lo, hi) <= INITIAL_CONTACT_WINDOW_PCT for ic in contacts] for lo, hi in spans]
        assert sorted(near) == [[False, True], [True, False]], (side, spans)  # one burst per contact
        peaks[side] = sorted(pct[max(range(a, b + 1), key=lambda k: curve[k % n]) % n] for a, b in runs)
    assert peaks["r"] == pytest.approx([7.0, 62.6], abs=2.0)
    assert peaks["l"] == pytest.approx([14.8, 47.8], abs=2.0)


@pytest.mark.parametrize("side", ["r", "l"])
def test_posterior_deltoid_drives_the_backward_arm_swing(run: Run, side: str) -> None:
    """The arm swings back from its most flexed to its most extended angle of the stride
    (right 50-97 %, left 0-57 %). The posterior deltoid peaks inside that swing (right 0.080 at
    60 %, left 0.123 at 10 %) and is a concentric main mover of shoulder extension in a phase
    where the shoulder extends: right pre-swing; left loading response and mid-stance."""
    coord = f"arm_flex_{side}"
    q = [run.kin.columns[coord][i] for i in run.frames]
    pct = [run.pct(run.act.time[i]) for i in run.frames]
    hi, lo = max(range(len(q)), key=lambda k: q[k]), min(range(len(q)), key=lambda k: q[k])
    a = [run.act.columns[f"DELT3_{side}"][i] for i in run.frames]
    peak = max(range(len(a)), key=lambda k: a[k])
    assert pct[hi] <= pct[peak] <= pct[lo] if hi < lo else (pct[peak] >= pct[hi] or pct[peak] <= pct[lo])
    driving = {
        ph: r for ph, r in run.roles_of(f"DELT3_{side}", coord).items()
        if run.action(ph, coord)["changeDeg"] < 0 and r == (-1, "mainMover", "concentric")
    }
    assert set(driving) == ({"preSwing"} if side == "r" else {"loadingResponse", "midStance"})


def test_neck_extensors_hold_the_head(run: Run) -> None:
    """With the head held level (D-010), the lower neck changes by under 5 degrees in every
    phase while the muscles' net moment extends it: the extensors hold the head against
    gravity. Splenius capitis (from the thorax, right) stabilises the neck in pre-swing (mean
    activation 0.1055, close above the 0.10 stabiliser floor); in the other six phases it helps
    extend it."""
    for p in run.roles["phases"]:
        a = run.action(p["phase"], "neck_lower_extension")
        assert a["stabilised"] and a["direction"] == 1, p["phase"]
    splenius = {m for m, e in run.enriched["muscles"].items() if any(g.startswith("spleniusCapitis_") for g in e["groups"])}
    held = {(p["phase"], m["muscle"]) for p in run.roles["phases"] for m in run.action(p["phase"], "neck_lower_extension")["muscles"] if m["muscle"] in splenius and m["role"] == "stabiliser"}
    assert held == {("preSwing", "splen_cap_sklthx_r")}


def test_arm_muscles_below_the_d006_floor(run: Run) -> None:
    """Arm swing is largely passive: 39 of the 94 arm muscles stay under the D-006 floor in all
    seven phases (pectoralis major, coracobrachialis, the lateral and medial triceps, anconeus,
    the pronators, extensor carpi radialis brevis, most finger muscles, and the right teres
    minor)."""
    cfg = label_roles.load_config(REPO / paths.ROLE_THRESHOLDS)
    groups = {f"{g}_{s}" for g in ARM_GROUPS for s in "rl"}
    arm = sorted(m for m, a in run.enriched["muscles"].items() if groups & set(a["groups"]))
    assert len(arm) == 94
    t = run.act.time
    bounds = [(p["start"], p["end"]) for p in run.roles["phases"]]
    below = set()
    for m in arm:
        x = run.act.columns[m]
        peak = max(x[i] for i in run.frames)
        means = []
        for t0, t1 in bounds:
            fr = [i for i, ti in enumerate(t) if t0 - 1e-9 <= ti <= t1 + 1e-9]
            means.append(label_roles.trapezoid([t[i] for i in fr], [x[i] for i in fr]) / (t[fr[-1]] - t[fr[0]]))
        if not any(label_roles.active(v, peak, cfg) for v in means):
            below.add(m)
    assert below == ARM_BELOW_FLOOR


def test_biceps_takes_no_forearm_rotation_role(run: Run) -> None:
    """The model's biceps moment arm about forearm rotation is 0.02-0.10 cm (right) and
    0.08-0.15 cm (left) on the pronation side, under the 5 mm floor (Holzbaur's biceps
    supinates with 0.44 cm; via points frozen at the mean arm pose). So the biceps takes no
    pronation or supination role, the graph has no `crosses` edge from it to the radio-ulnar
    joints, and the supinator alone supinates. At the elbow it works every phase."""
    r_min = run.roles["config"]["momentArmMinM"]
    arms: dict[str, list[float]] = {}
    with (WORK / "moment_arms.csv").open() as f:
        for row in csv.DictReader(f):
            if row["muscle"].startswith("BIC") and row["coordinate"].startswith("pro_sup"):
                arms.setdefault(row["muscle"], []).append(float(row["moment_arm"]))
    assert set(arms) == {"BIClong_r", "BICshort_r", "BIClong_l", "BICshort_l"}
    for m, r in arms.items():
        assert 0.0 < min(r) and max(r) < 0.002 < r_min, m  # pronation side, under 2 mm
    for side in "rl":
        for m in (f"BIClong_{side}", f"BICshort_{side}"):
            assert run.roles_of(m, f"pro_sup_{side}") == {}
            assert not any(c["muscle"] == m and c["coordinate"] == f"pro_sup_{side}" for c in run.roles["crosses"])
        sup = run.roles_of(f"SUP_{side}", f"pro_sup_{side}")
        assert len(sup) == 7 and {c for _, _, c in sup.values()} == {"isometric"}
    edges = {(e["source"], e["target"]) for e in run.graph["edges"] if e["relation"] == "crosses"}
    assert ("muscle:BIClong_r", "joint:radioulnar_r") not in edges and ("muscle:BIClong_r", "joint:elbow_r") in edges
    assert run.roles_of("BIClong_r", "elbow_flex_r") == {
        "loadingResponse": (1, "mainMover", "isometric"),
        "midStance": (1, "mainMover", "concentric"),
        "terminalStance": (1, "mainMover", "concentric"),
        "preSwing": (-1, "antagonist", "eccentric"),
        "initialSwing": (-1, "antagonist", "eccentric"),
        "midSwing": (1, "mainMover", "eccentric"),
        "terminalSwing": (1, "mainMover", "eccentric"),
    }
