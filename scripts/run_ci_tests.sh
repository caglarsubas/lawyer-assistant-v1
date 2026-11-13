#!/usr/bin/env bash
# Bounded disposable test files, with real SQLite locks and executable fixtures.
set -euo pipefail

if [[ "$#" -eq 0 ]]; then
  exit 2
fi
# Collection uses the identical command/partition without creating test storage.
for argument in "$@"; do
  if [[ "$argument" == "--collect-only" ]]; then
    exec "$@"
  fi
done

scratch=$(mktemp -d "${RUNNER_TEMP:?}/lawyer-test-memory.XXXXXX")
mounted=false
privilege=()
if [[ "$EUID" -ne 0 ]]; then
  privilege=(sudo)
fi
cleanup() {
  status=$?
  trap - EXIT
  if [[ "$mounted" == true ]] && ! "${privilege[@]}" umount "$scratch"; then
    status=1
  fi
  if ! rmdir "$scratch"; then
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
"${privilege[@]}" mount -t tmpfs -o size=1024m,mode=1777,nosuid,nodev tmpfs "$scratch"
mounted=true
# Preserve strict filesystem checks and give temporary bundle writes the same
# disposable filesystem as pytest fixtures.
if [[ "${GITHUB_ACTIONS:-}" == true ]]; then
  # xdist forwards the plugin to workers. Preserve the closed argv contracts
  # of the reserve guard and serial history runner.
  if [[ "$1" == */pytest || "$1" == pytest || ( "${2:-}" == -m && "${3:-}" == pytest ) || "${2:-}" == scripts/run_ci_reserve_guard_v3.py ]]; then
    export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
    set -- "$@" -p scripts.ci_worker_gc
  fi
fi
# Exec intentionally remains enabled: fake relay executables are real contracts.
TMPDIR="$scratch" "$@" --basetemp="$scratch/pytest"
