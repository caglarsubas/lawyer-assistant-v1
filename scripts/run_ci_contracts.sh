#!/usr/bin/env bash
# Bounded unit-test scratch with real SQLite locks. Native durability uses ext4.
set -euo pipefail
[[ "$#" -gt 0 ]]
scratch=$(mktemp -d "${RUNNER_TEMP:?}/lawyer-contract-memory.XXXXXX")
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
TMPDIR="$scratch" "$@"
