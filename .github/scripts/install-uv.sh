#!/usr/bin/env bash
# Public CI tool only. The caller enforces a 20-second whole-command deadline.
set -euo pipefail
umask 077
: "${RUNNER_TEMP:?}" "${GITHUB_PATH:?}"
[[ $(uname -s) == Linux ]] || exit 2
case "$(uname -m)" in
  aarch64)
    triple=uv-aarch64-unknown-linux-gnu
    expected=6ede0fefa7db7be3d5d9eda8784a8e43b1cf5410720eb3da60ab1d2f66678e82
    ;;
  x86_64)
    triple=uv-x86_64-unknown-linux-gnu
    expected=be9878e9d08ebcb621a683aba52e7fb8bbf92b2532e0d759026ffcc067673042
    ;;
  *) exit 2 ;;
esac
cache="${PIP_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/pip}/lawyer-ci-uv/0.8.15"
mkdir -p -- "$cache"
[[ -d $cache && ! -L $cache ]] || exit 2
archive="$cache/$triple-$expected.tar.gz"
pending=
target=
cleanup() {
  code=$?
  trap - EXIT
  [[ -z $pending ]] || rm -f -- "$pending"
  if [[ $code -ne 0 && -n $target ]]; then rm -rf -- "$target"; fi
  exit "$code"
}
trap cleanup EXIT
if [[ ! -e $archive && ! -L $archive ]]; then
  pending=$(mktemp "$cache/.download.XXXXXX")
  curl --fail --silent --show-error --proto '=https' --location --max-redirs 3 \
    --connect-timeout 5 --max-time 15 --retry 0 \
    "https://github.com/astral-sh/uv/releases/download/0.8.15/$triple.tar.gz" --output "$pending"
  printf '%s  %s\n' "$expected" "$pending" | sha256sum --check --status
  mv -- "$pending" "$archive"
  pending=
fi
# A cache hit confers no trust: verify bytes before extraction on every run.
[[ -f $archive && ! -L $archive ]] || exit 2
printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status
target=$(mktemp -d "$RUNNER_TEMP/lawyer-uv.XXXXXX")
tar -xzf "$archive" -C "$target" --strip-components=1 -- "$triple/uv"
[[ -f $target/uv && ! -L $target/uv && -x $target/uv ]] || exit 2
case "$("$target/uv" --version)" in
  'uv 0.8.15'|'uv 0.8.15 ('*) ;;
  *) exit 2 ;;
esac
printf '%s\n' "$target" >> "$GITHUB_PATH"
