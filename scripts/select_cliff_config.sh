#!/usr/bin/env bash
# Print the git-cliff config rust-release.yaml uses: the caller's cliff.toml in
# the current directory wins; otherwise the default shipped in this repository
# ($ACTIONS_DIR/cliff.toml). Shared by the release step and its self-test.
set -euo pipefail
if [ -f cliff.toml ]; then
  echo "${PWD}/cliff.toml"
else
  CFG="${ACTIONS_DIR:?ACTIONS_DIR is not set}/cliff.toml"
  if [ ! -f "$CFG" ]; then
    echo "::error::no cliff.toml in the caller and no default at ${CFG}" >&2
    exit 1
  fi
  echo "$CFG"
fi
