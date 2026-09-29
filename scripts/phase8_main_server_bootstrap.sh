#!/usr/bin/env bash
set -euo pipefail
TRANSFER_ROOT="${TRANSFER_ROOT:-/root}"
PROJECT_ROOT="/root/EASYkoopman-phase8-main-v2"
BUNDLE="$TRANSFER_ROOT/EasyUUV-phase8-main-v2.bundle"
EXPECTED="$TRANSFER_ROOT/expected-source-commit.txt"
[[ -f "$BUNDLE" && -f "$EXPECTED" ]] || { echo incomplete_bundle >&2; exit 1; }
[[ ! -e "$PROJECT_ROOT" ]] || { echo isolated_project_root_exists >&2; exit 1; }
expected_commit="$(tr -d '\r\n' < "$EXPECTED")"
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || { echo expected_source_commit_invalid >&2; exit 1; }
git clone "$BUNDLE" "$PROJECT_ROOT"
cd "$PROJECT_ROOT"
git checkout --detach "$expected_commit"
[[ "$(git rev-parse HEAD)" == "$expected_commit" ]] || { echo source_commit_mismatch >&2; exit 1; }
[[ -z "$(git -c core.excludesFile= status --porcelain=v1 --untracked-files=all)" ]] || { echo worktree_dirty >&2; exit 1; }
bash scripts/phase8_main_server_run.sh
