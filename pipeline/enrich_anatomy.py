"""Stage `enrichAnatomy`: names, ontology identifiers, attachments, and innervation for `roles`.

Inputs: `roles.json` (stage `labelRoles`), `model.json` (muscle path bodies, joint bodies),
`data/curated/anatomy.yaml` (hand-curated, format in its header), and the Uberon and FMA
subsets under `data/raw/ontology/` (`data/raw/ontology/fetch.sh` writes them with the `subset`
command of this module).

Entities. anatomy.yaml lists entities per kind: `bones`, `joints`, `muscles`, `groups`
(muscle groups), `ligaments`, `nerves`, `actions` (joint actions), `phases`, `movement`. An
entity's key gives its node: side `right` for a key ending in `_r`, `midline` otherwise.
`opensimName` is the model element: the muscle's own key, a bone's body, a joint's first
`opensim` joint.

Attachments. A muscle's origin bone is its `origin` in anatomy.yaml, else the bone that
`bodies` maps the first body of its model path to (`model.json` `originBody`); its insertion
likewise from `insertion` or the last body of the path. A curated bone must belong to a body on
the muscle's model path (`check_attachment`), so the curation refines the model and stays
consistent with it. A joint's `articulates` bones must belong to the parent or child bodies of
its `opensim` joints.

Ontology identifiers (`Ontology.lookup`). Each entity's lookup term is `fmaName` (FMA only),
else `ontologyName`, else `name`, compared case-insensitively.
  - Uberon: the term whose name equals the lookup term, else one with an EXACT synonym equal to
    it, else one with any other synonym equal to it; ties go to the lowest identifier. Uberon
    terms are species- and side-neutral.
  - FMA: for right-side entities the class labelled "Right <term>" (FMA models sides), else the
    class labelled <term>; label first, then FMA synonyms; ties go to the lowest identifier.
  An entity without a match gets `null` and the stage lists it. FMA serves identifiers alone,
  in line with its licence terms (`data/raw/ontology/SOURCES.md`).

Output `enriched.json`:
  sources      ontology versions read (`uberon`: data-version, `fma`: versionInfo)
  roles        the contents of `roles.json`
  entities     {kind: {key: {name, commonName, side, uberonId, fmaId, opensimName}}}, `kind`
               one of the schema's node kinds (`schema.KIND`)
  muscles      {key: {origin, insertion, groups, nerve}}: bone, group and nerve keys
  joints       {key: {articulates}}: bone keys
  ligaments    {key: {stabilises}}: joint keys
  coordinates  {coordinate: {joint, positive, negative}}: joint and action keys
  unresolved   [{kind, key, ontology, term}]: lookups without a match

Run from the repository root: `python -m pipeline.enrich_anatomy` (pure Python with PyYAML);
`python -m pipeline.enrich_anatomy subset --uberon-full F --fma-full G` writes the subsets.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pipeline.load_model import REPO
from pipeline.segment_phases import GENERATED

import pipeline_paths as paths  # noqa: E402  (generated/py: see `GENERATED`)

SECTIONS: dict[str, str] = {
    "bones": "bone",
    "joints": "joint",
    "muscles": "muscle",
    "groups": "muscleGroup",
    "ligaments": "ligament",
    "nerves": "nerve",
    "actions": "jointAction",
    "phases": "phase",
    "movement": "movement",
}
"""anatomy.yaml section -> node kind."""

ONTOLOGY_KINDS = ("bone", "joint", "muscle", "muscleGroup", "ligament", "nerve")
"""Node kinds looked up in the ontologies; actions, phases and movements are outside them."""

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
FMA_NS = "http://purl.org/sig/ont/fma/"


def side_of(key: str) -> str:
    return "right" if key.endswith("_r") else "midline"


# ---------------------------------------------------------------------------------------------
# Ontologies.


@dataclass
class Term:
    """An ontology term: identifier, label, synonyms with their scope (EXACT, RELATED, ... for
    Uberon; `synonym` for FMA), and the source text kept by the subsets."""

    id: str
    label: str
    synonyms: list[tuple[str, str]] = field(default_factory=list)
    text: str = ""


def id_number(term_id: str) -> int:
    m = re.search(r"(\d+)$", term_id)
    return int(m.group(1)) if m else 0


@dataclass
class Ontology:
    """Terms of one ontology, indexed by lower-case label and synonym."""

    terms: list[Term]
    version: str

    def lookup(self, text: str) -> str | None:
        """Identifier of the best term for `text`: label, then EXACT synonym, then any synonym."""
        want = text.lower()
        best: tuple[int, int, str] | None = None
        for t in self.terms:
            rank = 0 if t.label.lower() == want else None
            if rank is None:
                scopes = [s for syn, s in t.synonyms if syn.lower() == want]
                if not scopes:
                    continue
                rank = 1 if "EXACT" in scopes else 2
            cand = (rank, id_number(t.id), t.id)
            if best is None or cand < best:
                best = cand
        return best[2] if best else None


OBO_SYNONYM = re.compile(r'^synonym: "((?:[^"\\]|\\.)*)" (\w+)')


def parse_obo(text: str) -> tuple[list[str], list[Term]]:
    """Header lines and the non-obsolete `[Term]` stanzas of an OBO file."""
    blocks = re.split(r"\n(?=\[)", text)
    header = blocks[0].splitlines()
    terms: list[Term] = []
    for block in blocks[1:]:
        if not block.startswith("[Term]"):
            continue
        tid = name = ""
        syns: list[tuple[str, str]] = []
        obsolete = False
        for line in block.splitlines():
            if line.startswith("id: "):
                tid = line[4:].strip()
            elif line.startswith("name: "):
                name = line[6:].strip()
            elif line.startswith("is_obsolete: true"):
                obsolete = True
            else:
                m = OBO_SYNONYM.match(line)
                if m:
                    syns.append((m.group(1), m.group(2)))
        if tid and not obsolete:
            terms.append(Term(tid, name, syns, block.rstrip("\n")))
    return header, terms


def read_uberon(path: Path) -> Ontology:
    header, terms = parse_obo(path.read_text())
    version = next((h.split(": ", 1)[1] for h in header if h.startswith("data-version: ")), "")
    return Ontology([t for t in terms if t.id.startswith("UBERON:")], version)


def read_fma(path: Path) -> Ontology:
    """FMA classes of an OWL (RDF/XML) file: `rdfs:label`, `fma:synonym`,
    `fma:preferred_name`, `fma:FMAID`. Streams the file, so the full release (≈200 MB) fits."""
    terms: list[Term] = []
    version = ""
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == f"{{{OWL}}}versionInfo" and not version:
            version = (el.text or "").strip()
        if el.tag != f"{{{OWL}}}Class":
            continue
        fid = el.findtext(f"{{{FMA_NS}}}FMAID")
        label = el.findtext(f"{{{RDFS}}}label")
        if fid and label:
            syns = [(s.text or "", "synonym") for s in el.findall(f"{{{FMA_NS}}}synonym")]
            pref = el.findtext(f"{{{FMA_NS}}}preferred_name")
            if pref and pref != label:
                syns.append((pref, "synonym"))
            terms.append(Term(f"FMA:{fid.strip()}", label.strip(), syns))
        el.clear()
    return Ontology(terms, version)


def write_obo_subset(path: Path, header: Sequence[str], terms: Iterable[Term]) -> int:
    keep = [h for h in header if h.split(":", 1)[0] in ("format-version", "data-version", "ontology")]
    body = [t.text for t in sorted(terms, key=lambda t: id_number(t.id))]
    path.write_text("\n".join(keep) + "\n\n" + "\n\n".join(body) + "\n")
    return len(body)


def write_fma_subset(path: Path, version: str, terms: Iterable[Term]) -> int:
    ET.register_namespace("rdf", RDF)
    ET.register_namespace("rdfs", RDFS)
    ET.register_namespace("owl", OWL)
    ET.register_namespace("fma", FMA_NS)
    root = ET.Element(f"{{{RDF}}}RDF")
    onto = ET.SubElement(root, f"{{{OWL}}}Ontology", {f"{{{RDF}}}about": "http://purl.org/sig/ont/fma.owl"})
    ET.SubElement(onto, f"{{{OWL}}}versionInfo").text = version
    n = 0
    for t in sorted(terms, key=lambda t: id_number(t.id)):
        num = t.id.split(":", 1)[1]
        c = ET.SubElement(root, f"{{{OWL}}}Class", {f"{{{RDF}}}about": f"{FMA_NS}fma{num}"})
        ET.SubElement(c, f"{{{RDFS}}}label").text = t.label
        ET.SubElement(c, f"{{{FMA_NS}}}FMAID").text = num
        for syn, _ in t.synonyms:
            ET.SubElement(c, f"{{{FMA_NS}}}synonym").text = syn
        n += 1
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return n


# ---------------------------------------------------------------------------------------------
# Curated anatomy.


def load_anatomy(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    return data


def lookup_terms(kind: str, key: str, entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The Uberon and FMA lookup terms of an entity, in preference order."""
    base = str(entry.get("ontologyName", entry["name"]))
    fma = str(entry.get("fmaName", base))
    fma_terms = ([f"right {fma}"] if side_of(key) == "right" else []) + [fma]
    return [base], fma_terms


def wanted_terms(anatomy: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Every lower-case lookup term of anatomy.yaml, for Uberon and for FMA."""
    ub: set[str] = set()
    fm: set[str] = set()
    for section, kind in SECTIONS.items():
        if kind not in ONTOLOGY_KINDS:
            continue
        for key, entry in anatomy[section].items():
            u, f = lookup_terms(kind, key, entry)
            ub.update(x.lower() for x in u)
            fm.update(x.lower() for x in f)
    return ub, fm


def matches(t: Term, wanted: set[str]) -> bool:
    return t.label.lower() in wanted or any(s.lower() in wanted for s, _ in t.synonyms)


def subset(anatomy_path: Path, uberon_full: Path, fma_full: Path, uberon_out: Path, fma_out: Path) -> tuple[int, int]:
    """Write the Uberon and FMA terms that anatomy.yaml's lookup terms match."""
    ub, fm = wanted_terms(load_anatomy(anatomy_path))
    header, terms = parse_obo(uberon_full.read_text())
    n_ub = write_obo_subset(uberon_out, header, (t for t in terms if t.id.startswith("UBERON:") and matches(t, ub)))
    fma = read_fma(fma_full)
    n_fma = write_fma_subset(fma_out, fma.version, (t for t in fma.terms if matches(t, fm)))
    return n_ub, n_fma


def check_attachment(muscle: str, role: str, bone: str, bones: dict[str, Any], path_bodies: Sequence[str]) -> None:
    body = bones[bone]["body"]
    if body not in path_bodies:
        raise ValueError(f"{muscle}: {role} bone {bone} belongs to {body}, off the model path {list(path_bodies)}")


def enrich(roles: dict[str, Any], model: dict[str, Any], anatomy: dict[str, Any], uberon: Ontology, fma: Ontology) -> dict[str, Any]:
    """The contents of `enriched.json`."""
    bones = anatomy["bones"]
    muscles_model = {m["name"]: m for m in model["muscles"]}
    joints_model = {j["name"]: j for j in model["joints"]}
    unresolved: list[dict[str, str]] = []
    entities: dict[str, dict[str, Any]] = {}
    for section, kind in SECTIONS.items():
        out: dict[str, Any] = {}
        for key, entry in anatomy[section].items():
            if kind == "muscle" and key not in roles["muscles"]:
                continue
            uid = fid = None
            if kind in ONTOLOGY_KINDS:
                u_terms, f_terms = lookup_terms(kind, key, entry)
                uid = next((x for x in (uberon.lookup(t) for t in u_terms) if x), None)
                fid = next((x for x in (fma.lookup(t) for t in f_terms) if x), None)
                if uid is None:
                    unresolved.append({"kind": kind, "key": key, "ontology": "uberon", "term": u_terms[0]})
                if fid is None:
                    unresolved.append({"kind": kind, "key": key, "ontology": "fma", "term": f_terms[-1]})
            opensim: str | None = None
            if kind == "muscle":
                opensim = key
            elif kind == "bone":
                opensim = str(entry["body"])
            elif kind == "joint":
                opensim = str(entry["opensim"][0])
            out[key] = {
                "name": entry["name"],
                "commonName": entry.get("commonName"),
                "side": side_of(key),
                "uberonId": uid,
                "fmaId": fid,
                "opensimName": opensim,
            }
        entities[kind] = out

    missing = sorted(set(roles["muscles"]) - set(anatomy["muscles"]))
    if missing:
        raise ValueError(f"anatomy.yaml lacks muscles {missing}")
    muscles: dict[str, Any] = {}
    for key in roles["muscles"]:
        entry = anatomy["muscles"][key]
        mm = muscles_model[key]
        origin = entry.get("origin", anatomy["bodies"][mm["originBody"]])
        insertion = entry.get("insertion", anatomy["bodies"][mm["insertionBody"]])
        check_attachment(key, "origin", origin, bones, mm["pathBodies"])
        check_attachment(key, "insertion", insertion, bones, mm["pathBodies"])
        for g in entry["groups"]:
            if g not in anatomy["groups"]:
                raise ValueError(f"{key}: unknown group {g}")
        if entry["nerve"] not in anatomy["nerves"]:
            raise ValueError(f"{key}: unknown nerve {entry['nerve']}")
        muscles[key] = {"origin": origin, "insertion": insertion, "groups": list(entry["groups"]), "nerve": entry["nerve"]}

    joints: dict[str, Any] = {}
    for key, entry in anatomy["joints"].items():
        bodies = set()
        for j in entry["opensim"]:
            bodies |= {joints_model[j]["parent"], joints_model[j]["child"]}
        for b in entry["articulates"]:
            if bones[b]["body"] not in bodies:
                raise ValueError(f"joint {key}: bone {b} lies off the bodies {sorted(bodies)}")
        joints[key] = {"articulates": list(entry["articulates"])}

    ligaments: dict[str, Any] = {}
    for key, entry in anatomy["ligaments"].items():
        for j in entry["stabilises"]:
            if j not in anatomy["joints"]:
                raise ValueError(f"ligament {key}: unknown joint {j}")
        ligaments[key] = {"stabilises": list(entry["stabilises"])}

    coordinates: dict[str, Any] = {}
    for coord in roles["config"]["coordinates"]:
        entry = anatomy["coordinates"].get(coord)
        if entry is None:
            raise ValueError(f"anatomy.yaml lacks coordinate {coord}")
        for k in ("positive", "negative"):
            if entry[k] not in anatomy["actions"]:
                raise ValueError(f"coordinate {coord}: unknown action {entry[k]}")
        coordinates[coord] = {"joint": entry["joint"], "positive": entry["positive"], "negative": entry["negative"]}

    return {
        "sources": {"uberon": uberon.version, "fma": fma.version},
        "roles": roles,
        "entities": entities,
        "muscles": muscles,
        "joints": joints,
        "ligaments": ligaments,
        "coordinates": coordinates,
        "unresolved": unresolved,
    }


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["subset"]:
        sp = argparse.ArgumentParser(prog="python -m pipeline.enrich_anatomy subset", description="Write the Uberon and FMA subsets.")
        sp.add_argument("--anatomy", type=Path, default=REPO / paths.CURATED_ANATOMY)
        sp.add_argument("--uberon-full", type=Path, required=True)
        sp.add_argument("--fma-full", type=Path, required=True)
        sp.add_argument("--uberon-out", type=Path, default=REPO / paths.UBERON)
        sp.add_argument("--fma-out", type=Path, default=REPO / paths.FMA)
        s = sp.parse_args(argv[1:])
        n_ub, n_fma = subset(s.anatomy, s.uberon_full, s.fma_full, s.uberon_out, s.fma_out)
        print(f"enrich_anatomy subset: {n_ub} Uberon terms -> {s.uberon_out}, {n_fma} FMA classes -> {s.fma_out}")
        return 0
    ap = argparse.ArgumentParser(prog="python -m pipeline.enrich_anatomy", description=doc.split("\n")[0])
    ap.add_argument("--roles", type=Path, default=REPO / paths.ROLES)
    ap.add_argument("--model", type=Path, default=REPO / paths.MODEL)
    ap.add_argument("--uberon", type=Path, default=REPO / paths.UBERON)
    ap.add_argument("--fma", type=Path, default=REPO / paths.FMA)
    ap.add_argument("--anatomy", type=Path, default=REPO / paths.CURATED_ANATOMY)
    ap.add_argument("--out", type=Path, default=REPO / paths.ENRICHED)
    a = ap.parse_args(argv)
    out = enrich(
        json.loads(a.roles.read_text()),
        json.loads(a.model.read_text()),
        load_anatomy(a.anatomy),
        read_uberon(a.uberon),
        read_fma(a.fma),
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    for u in out["unresolved"]:
        print(f"  unresolved {u['ontology']}: {u['kind']} {u['key']} ({u['term']})")
    print(f"enrich_anatomy: {sum(len(v) for v in out['entities'].values())} entities, {len(out['unresolved'])} unresolved lookups; wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
