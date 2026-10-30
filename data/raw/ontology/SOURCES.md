# Sources and licences of `data/raw/ontology/`

Facts live in `fetch.sh` (URLs, pinned checksums) and `pipeline/enrich_anatomy.py` (how the
subsets are cut and how terms are matched). This note records provenance and licence terms.
Files fetched 2026-10-29. Every file here except this note and `fetch.sh` is git-ignored
(`*.obo`, `*.owl`); `fetch.sh` recreates them, and stage `enrichAnatomy` then runs offline.

| File | Content |
|---|---|
| `uberon-full.obo` | Uberon release `releases/2026-10-01` (OBO format, 22.5 MB) |
| `fma-full.owl` | FMA 5.1.0 (OWL, RDF/XML, 208 MB) |
| `uberon.obo` | Subset: the Uberon terms whose name or synonym equals a lookup term of `data/curated/anatomy.yaml` (≈ 70 terms), stanzas copied verbatim |
| `fma.owl` | Subset: the FMA classes whose label or synonym equals a lookup term (≈ 140 classes), with label, synonyms and FMAID only |

## Uberon

| Item | Value |
|---|---|
| Project | Uberon multi-species anatomy ontology, https://obophenotype.github.io/uberon/ |
| Fetched from | https://github.com/obophenotype/uberon/releases/download/v2026-10-01/uberon.obo (target of http://purl.obolibrary.org/obo/uberon.obo on 2026-10-29) |
| Licence | CC BY 3.0, http://creativecommons.org/licenses/by/3.0/ (the file's own `dcterms-license`). Attribution: Mungall CJ, Torniai C, Gkoutos GV, Lewis SE, Haendel MA (2012). Uberon, an integrative multi-species anatomy ontology. Genome Biology 13:R5. https://doi.org/10.1186/gb-2012-13-1-r5 |
| Use | `uberonId` of bone, joint, muscle, muscle-group, ligament and nerve nodes in `data/out/graph.json` |

## FMA

| Item | Value |
|---|---|
| Project | Foundational Model of Anatomy, University of Washington Structural Informatics Group, http://si.washington.edu/projects/fma |
| Fetched from | http://sig.biostr.washington.edu/share/downloads/fma/release/latest/fma.owl (target of http://purl.obolibrary.org/obo/fma.owl on 2026-10-29), version 5.1.0 (`owl:versionInfo`; version IRI http://purl.org/sig/ont/fma_5.1.0.owl) |
| Licence | Custom: the OBO Foundry registry lists "CUSTOM" and points to http://sig.biostr.washington.edu/projects/fm/FMA_Release, which offers a "Draft Open Source FMA License" (2006 draft); see `data/raw/SOURCES.md`. |
| Use | Identifiers only: the `fmaId` of nodes in `data/out/graph.json` (side-specific classes such as "Right gluteus medius" where FMA has them). The project redistributes no FMA content: the full file and the subset stay local and git-ignored, and the graph carries FMA identifiers alone. |
