#!/usr/bin/env bash
# Idempotent: install micromamba if absent, create/update the OpenSim env, print its Python.
# Facts: OpenSim 4.6 from the opensim-org channel supports Python 3.9-3.12 (not the
# system Python 3.14), so the pipeline runs with the env's interpreter printed last.
# Overrides: BM_ENV_PREFIX (default $HOME/.local/share/bm-opensim), BM_MM_BIN_DIR
# (default $HOME/.local/bin), MAMBA_ROOT_PREFIX (default $HOME/.local/share/mamba).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
prefix="${BM_ENV_PREFIX:-$HOME/.local/share/bm-opensim}"
bindir="${BM_MM_BIN_DIR:-$HOME/.local/bin}"
export MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/.local/share/mamba}"
export PATH="$bindir:$PATH"

if ! command -v micromamba >/dev/null 2>&1; then
  echo "setup: installing micromamba into $bindir" >&2
  mkdir -p "$bindir"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/latest -o "$tmp/mm.tar.bz2"
  tar -xjf "$tmp/mm.tar.bz2" -C "$tmp" bin/micromamba
  install -m755 "$tmp/bin/micromamba" "$bindir/micromamba"
fi

if [ -x "$prefix/bin/python" ]; then
  echo "setup: updating env at $prefix" >&2
  micromamba install -y -q -p "$prefix" -f "$here/environment.yml"
else
  echo "setup: creating env at $prefix" >&2
  micromamba create -y -q -p "$prefix" -f "$here/environment.yml"
fi

"$prefix/bin/python" -c "import opensim; print('opensim', opensim.GetVersionAndDate(), file=__import__('sys').stderr)"
echo "$prefix/bin/python"
