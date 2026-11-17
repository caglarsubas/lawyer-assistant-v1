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
unmount_scratch() {
  for attempt in 1 2 3 4 5; do
    if "${privilege[@]}" umount "$scratch" 2>/dev/null; then
      return 0
    fi
    sleep 0.1
  done
  "${privilege[@]}" umount "$scratch"
}
cleanup() {
  status=$?
  trap - EXIT
  if [[ "$mounted" == true ]] && ! unmount_scratch; then
    if [[ "$status" -eq 0 ]]; then
      status=1
    fi
    exit "$status"
  fi
  if ! rmdir "$scratch" && [[ "$status" -eq 0 ]]; then
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
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
TMPDIR="$scratch" python3 "$(dirname -- "${BASH_SOURCE[0]}")/run_ci_test_process.py" "$@" --basetemp="$scratch/pytest"
