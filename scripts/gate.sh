#!/usr/bin/env bash
# The gate (plan.md): every branch passes it before merge, and main passes it at every commit.
# Run from anywhere inside a checkout: scripts/gate.sh
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
py="${PYTHON:-$root/.venv/bin/python}"
[ -x "$py" ] || py="$(git worktree list --porcelain | head -1 | cut -d' ' -f2)/.venv/bin/python"
step() { printf '\n== %s\n' "$*"; }

step "lake build"
log="$(cd spec && lake build 2>&1)" || { echo "$log"; exit 1; }
if grep -q "declaration uses 'sorry'" <<<"$log"; then grep -B2 "declaration uses 'sorry'" <<<"$log"; exit 1; fi
echo ok

step "lake exe gen + arch export: empty diff under generated/"
(cd spec && lake exe gen >/dev/null && lake exe arch export >/dev/null)
git diff --exit-code -- generated/
untracked="$(git ls-files --others --exclude-standard -- generated/)"
[ -z "$untracked" ] || { echo "untracked generated files:"; echo "$untracked"; exit 1; }
echo ok

step "lake exe arch check"
(cd spec && lake exe arch check 2>&1 | tail -n +1 | grep -vE '^(⚠|✔|warning|trace)')

step "lake exe arch print --detail 0"
(cd spec && lake exe arch print --detail 0 2>&1 | grep -vE '^(⚠|✔|warning|trace)')

step "checkGraph and conform on fixtures"
q() { grep -vE '^(⚠|✔|warning|trace)' || true; }
(cd spec && lake exe checkGraph ../data/fixtures/graph.sample.json 2>&1 | q; exit "${PIPESTATUS[0]}")
if (cd spec && lake exe checkGraph ../data/fixtures/graph.bad-edge.json >/dev/null 2>&1); then echo "checkGraph accepted graph.bad-edge.json"; exit 1; fi
(cd spec && lake exe conform ../data/fixtures/trace.sample.json 2>&1 | q; exit "${PIPESTATUS[0]}")
for bad in trace.bad-gait.json trace.bad-ui.json; do
  if (cd spec && lake exe conform "../data/fixtures/$bad" >/dev/null 2>&1); then echo "conform accepted $bad"; exit 1; fi
done

step "mypy"
targets=(generated/py tests)
for d in pipeline tools; do [ -d "$d" ] && targets+=("$d"); done
"$py" -m mypy "${targets[@]}"

if [ -f web/package.json ]; then
  step "tsc"
  (cd web && npx --no-install tsc --noEmit)
  step "npm test, recorded trace through lake exe conform"
  trace="$(mktemp --suffix=.json)"
  (cd web && BM_TRACE_OUT="$trace" npm test --silent)
  (cd spec && lake exe conform "$trace" 2>&1 | grep -vE '^(⚠|✔|warning|trace:)' || true; exit "${PIPESTATUS[0]}")
  rm -f "$trace"
fi

step "pytest"
"$py" -m pytest -q

# OpenSim tests need the pipeline env (pipeline/env/setup.sh); the step runs when it exists.
osim_py="$HOME/.local/share/bm-opensim/bin/python"
if [ -x "$osim_py" ] && [ "${GATE_SKIP_OPENSIM:-0}" != 1 ]; then
  step "pytest with OpenSim"
  "$osim_py" -m pytest -q pipeline/tests
fi

printf '\ngate: pass\n'
