#!/usr/bin/env bash
# Fetch Uberon and FMA, check them, and write the subsets stage enrichAnatomy reads:
#   data/raw/ontology/uberon.obo   Uberon terms matching the lookup terms of data/curated/anatomy.yaml
#   data/raw/ontology/fma.owl      FMA classes matching them (identifiers and labels only)
# The full downloads stay beside them as uberon-full.obo and fma-full.owl. Every file here is
# git-ignored (*.obo, *.owl); provenance and licences: SOURCES.md in this directory.
# Run from anywhere inside a checkout, after editing anatomy.yaml too: data/raw/ontology/fetch.sh
# Matching rules: pipeline/enrich_anatomy.py (`subset`, `Ontology.lookup`).
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
dir="$root/data/raw/ontology"
py="${PYTHON:-$HOME/.local/share/bm-opensim/bin/python}"

UBERON_URL="https://github.com/obophenotype/uberon/releases/download/v2026-10-01/uberon.obo"
UBERON_SHA256="d4751a15d7551a8414caee2628c62bf68301d567caf54ccfa3eef383ae7cbb61"
FMA_URL="http://sig.biostr.washington.edu/share/downloads/fma/release/latest/fma.owl"
FMA_SHA256="beb3dc47979ad5434ef70fd02af4307f147f2023f7d8c2c57103b995191194c3"  # FMA 5.1.0

fetch() {  # url sha256 file
  if [ -f "$3" ] && echo "$2  $3" | sha256sum -c --quiet - 2>/dev/null; then return; fi
  curl -fSL --retry 3 -o "$3.part" "$1"
  echo "$2  $3.part" | sha256sum -c --quiet - || { echo "checksum mismatch: $1 (upstream changed; update the pin)"; exit 1; }
  mv "$3.part" "$3"
}

fetch "$UBERON_URL" "$UBERON_SHA256" "$dir/uberon-full.obo"
fetch "$FMA_URL" "$FMA_SHA256" "$dir/fma-full.owl"
cd "$root"
"$py" -m pipeline.enrich_anatomy subset --uberon-full "$dir/uberon-full.obo" --fma-full "$dir/fma-full.owl"
