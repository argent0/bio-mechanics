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
#
# Upper-body sources (Wave 1, D2), each pinned to one commit and login-free:
#   data/raw/holzbaur/    Holzbaur 2005 Stanford-VA upper limb (50 muscles), from
#                         mitkof6/OpenSimDatabase; Stanford_VA_Upper_Limb_original.osim, Geometry/*.vtp
#   data/raw/mortensen/   Mortensen 2018 HYOID 1.2 head and neck (72 muscles), from
#                         MyoHub/myoconverter; the .osim, license, notes.txt, Geometry/*.vtp
#   data/raw/christophy/  Christophy 2012 lumbar model: simtk.org needs a login, so the file is
#                         placed by hand. The script skips with a message while the folder holds
#                         no files, verifies them against SHA256SUMS once recorded, and
#                         records them with --record-christophy.
# data/raw/SHA256SUMS lists every fetched file, paths relative to data/raw/.
# Use: pipeline/env/fetch_data.sh [--no-derive] [--record-christophy]
#      (derive needs the env from setup.sh)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
raw="$root/data/raw"
dst="$raw/rajagopal"
sha="d9b05d470b1a481c222372c85b75772faf8f7792"   # opensim-org/opensim-models, 2025-11-05
base="https://raw.githubusercontent.com/opensim-org/opensim-models/$sha"
prefix="${BM_ENV_PREFIX:-$HOME/.local/share/bm-opensim}"
derive=1; record_christophy=0
for arg in "$@"; do
  case "$arg" in
    --no-derive) derive=0 ;;
    --record-christophy) record_christophy=1 ;;
    *) echo "fetch_data: unknown option $arg" >&2; exit 2 ;;
  esac
done

# fetch REMOTE_PATH LOCAL_PATH: skip when present, otherwise download atomically.
# Reads $dst (target folder) and $base (raw-content URL prefix) from the environment.
fetch() {
  local out="$dst/$2"
  [ -s "$out" ] && return 0
  mkdir -p "$(dirname "$out")"
  curl -fsSL --retry 3 "$base/$1" -o "$out.part" && mv "$out.part" "$out"
}
export -f fetch

model="Models/Rajagopal"
pipe="Pipelines/Rajagopal"
fetch "$model/Rajagopal2016.osim" Rajagopal2016.osim
fetch "$model/README.txt" README_upstream.txt

# Geometry: exactly the meshes the model names.
meshes="$(grep -o '<mesh_file>[^<]*</mesh_file>' "$dst/Rajagopal2016.osim" | sed 's/<[^>]*>//g' | sort -u)"
export dst base
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

# Holzbaur 2005 upper limb (BSD-3). The model names its bone meshes with <geometry_file>.
dst="$raw/holzbaur"
base="https://raw.githubusercontent.com/mitkof6/OpenSimDatabase/091168791bf007adb792c0c62488b57fff91de1a"
hz="upper_limb/complex/Stanford_VA_upper_limb"
fetch "$hz/Stanford_VA_Upper_Limb_original.osim" Stanford_VA_Upper_Limb_original.osim
meshes="$(grep -o '<geometry_file>[^<]*</geometry_file>' "$dst/Stanford_VA_Upper_Limb_original.osim" | sed 's/<[^>]*>//g' | sort -u)"
export dst base hz
printf '%s\n' $meshes | xargs -P 8 -I{} bash -c 'fetch "$hz/Geometry/{}" "Geometry/{}"'

# Mortensen 2018 HYOID 1.2 head and neck (MIT). The model names its meshes with <mesh_file>.
dst="$raw/mortensen"
base="https://raw.githubusercontent.com/MyoHub/myoconverter/cadf38059367a51239e6dc28c9fbe8b8fbd5149f"
mo="models/osim/Neck6D"
for f in HYOID_1.2_ScaledStrenght_UpdatedInertia.osim license notes.txt; do fetch "$mo/$f" "$f"; done
meshes="$(grep -o '<mesh_file>[^<]*</mesh_file>' "$dst/HYOID_1.2_ScaledStrenght_UpdatedInertia.osim" | sed 's/<[^>]*>//g' | sort -u)"
export dst base mo
printf '%s\n' $meshes | xargs -P 8 -I{} bash -c 'fetch "$mo/Geometry/{}" "Geometry/{}"'

# Christophy 2012 lumbar model: placed by hand (simtk.org group 567 needs a login).
chr="$raw/christophy"
chr_files() { find "$chr" -type f ! -name 'README*' ! -name '.*' -printf '%P\n' 2>/dev/null | LC_ALL=C sort; }
if [ "$record_christophy" = 1 ]; then
  [ -n "$(chr_files)" ] || { echo "fetch_data: --record-christophy found no files in $chr" >&2; exit 1; }
  { grep -v '  \./christophy/' "$raw/SHA256SUMS" || true; } > "$raw/SHA256SUMS.new"
  (cd "$chr" && chr_files | sed 's#^#./#' | xargs -d '\n' sha256sum | sed 's#  \./#  ./christophy/#') >> "$raw/SHA256SUMS.new"
  LC_ALL=C sort -k2 "$raw/SHA256SUMS.new" > "$raw/SHA256SUMS" && rm "$raw/SHA256SUMS.new"
  echo "fetch_data: recorded $(chr_files | wc -l) Christophy file(s) in SHA256SUMS" >&2
fi

# Checksums: SHA256SUMS lists paths relative to data/raw/.
sums="$(mktemp)"; chr_sums="$(mktemp)"; trap 'rm -f "$sums" "$chr_sums"' EXIT
grep -v '  \./christophy/' "$raw/SHA256SUMS" > "$sums"
grep '  \./christophy/' "$raw/SHA256SUMS" > "$chr_sums" || true
(cd "$raw" && sha256sum --quiet -c "$sums") || { echo "fetch_data: checksum mismatch" >&2; exit 1; }
echo "fetch_data: downloads verified ($(wc -l < "$sums") files)" >&2

if [ -z "$(chr_files)" ]; then
  echo "fetch_data: christophy skipped, data/raw/christophy/ holds no files (manual download from simtk.org group 567, then rerun with --record-christophy)" >&2
elif [ -s "$chr_sums" ]; then
  (cd "$raw" && sha256sum --quiet -c "$chr_sums") || { echo "fetch_data: christophy checksum mismatch" >&2; exit 1; }
  echo "fetch_data: christophy verified ($(wc -l < "$chr_sums") files)" >&2
else
  echo "fetch_data: christophy files present with no checksums recorded; rerun with --record-christophy" >&2
fi

if [ "$derive" = 1 ]; then
  [ -x "$prefix/bin/python" ] || { echo "fetch_data: run pipeline/env/setup.sh first" >&2; exit 1; }
  "$prefix/bin/python" -I "$here/make_trial.py" "$raw/rajagopal"
fi
