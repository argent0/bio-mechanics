#!/usr/bin/env bash
# Idempotent: fetch the Rajagopal full-body model, its geometry, and the walking trial
# into data/raw/rajagopal/, verify checksums, then derive scaled model + inverse kinematics.
#
# Source (login-free): GitHub opensim-org/opensim-models, pinned to one commit so the
# bytes never change. It redistributes the SimTK project https://simtk.org/projects/full_body
# (Rajagopal et al. 2016; simtk.org needs a login for downloads and answered too slowly to use).
#   Models/Rajagopal/Rajagopal2016.osim   the 80-muscle full-body model (OpenSim 4.5 format)
#   Geometry/*.vtp                        bone meshes the model references
#   Pipelines/Rajagopal/...               subject-11 walking trial: markers (.trc), ground
#                                         reaction forces (.mot), scale/IK/external-loads setups
# The upstream repo ships no inverse-kinematics result, so make_trial.py runs the upstream
# scale + IK setups to produce the coordinates .mot (the same recipe as the SimTK pipeline).
#
# Layout under data/raw/rajagopal/:
#   Rajagopal2016.osim, Geometry/*.vtp
#   walk_pipeline/   mirrors Pipelines/Rajagopal (ExpData, Scale, IK, ID); generic_unscaled.osim
#                    and Geometry (also under Scale/) are symlinks to the files above, as the
#                    upstream setups expect.
# Use: pipeline/env/fetch_data.sh [--no-derive]   (derive needs the env from setup.sh)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
raw="$root/data/raw"
dst="$raw/rajagopal"
sha="d9b05d470b1a481c222372c85b75772faf8f7792"   # opensim-org/opensim-models, 2025-11-05
base="https://raw.githubusercontent.com/opensim-org/opensim-models/$sha"
prefix="${BM_ENV_PREFIX:-$HOME/.local/share/bm-opensim}"
derive=1; [ "${1:-}" = "--no-derive" ] && derive=0

# fetch REMOTE_PATH LOCAL_PATH: skip when present, otherwise download atomically.
fetch() {
  local out="$dst/$2"
  [ -s "$out" ] && return 0
  mkdir -p "$(dirname "$out")"
  curl -fsSL --retry 3 "$base/$1" -o "$out.part" && mv "$out.part" "$out"
}

model="Models/Rajagopal"
pipe="Pipelines/Rajagopal"
fetch "$model/Rajagopal2016.osim" Rajagopal2016.osim
fetch "$model/README.txt" README_upstream.txt

# Geometry: exactly the meshes the model names.
meshes="$(grep -o '<mesh_file>[^<]*</mesh_file>' "$dst/Rajagopal2016.osim" | sed 's/<[^>]*>//g' | sort -u)"
export -f fetch; export dst base
printf '%s\n' $meshes | xargs -P 8 -I{} bash -c 'fetch "Geometry/{}" "Geometry/{}"'

# Walking trial: data, then tool setups.
for f in grf_walk.mot motion_capture_walk.trc static_walk_1.trc static_walk_2.trc; do
  fetch "$pipe/ExpData/$f" "walk_pipeline/ExpData/$f"
done
for f in markerset_walk_preScale.xml scale_setup_walk_scaleOnly.xml scale_setup_walk.xml; do
  fetch "$pipe/Scale/$f" "walk_pipeline/Scale/$f"
done
fetch "$pipe/IK/ik_setup_walk.xml" walk_pipeline/IK/ik_setup_walk.xml
fetch "$pipe/ID/grf_walk.xml" walk_pipeline/ID/grf_walk.xml

ln -sfn ../Rajagopal2016.osim "$dst/walk_pipeline/generic_unscaled.osim"
ln -sfn ../Geometry "$dst/walk_pipeline/Geometry"
ln -sfn ../../Geometry "$dst/walk_pipeline/Scale/Geometry"

# Checksums of everything fetched (SHA256SUMS lists paths relative to data/raw/rajagopal).
(cd "$dst" && sha256sum --quiet -c "$raw/SHA256SUMS") || { echo "fetch_data: checksum mismatch" >&2; exit 1; }
echo "fetch_data: downloads verified ($(wc -l < "$raw/SHA256SUMS") files)" >&2

if [ "$derive" = 1 ]; then
  [ -x "$prefix/bin/python" ] || { echo "fetch_data: run pipeline/env/setup.sh first" >&2; exit 1; }
  "$prefix/bin/python" -I "$here/make_trial.py" "$dst"
fi
