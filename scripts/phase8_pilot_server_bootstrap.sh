#!/usr/bin/env bash
set -Eeuo pipefail

readonly BUNDLE="/root/EasyUUV-phase8-pilot-v2.bundle"
readonly EXPECTED_COMMIT_FILE="/root/expected-source-commit.txt"
readonly TARGET="/root/EASYkoopman-phase8-pilot-v2"
readonly BRANCH="v2.0-multi-configuration"

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

[[ -f "$BUNDLE" ]] || die "bundle_missing"
[[ -f "$EXPECTED_COMMIT_FILE" ]] || die "expected_commit_sidecar_missing"
[[ ! -e "$TARGET" ]] || die "target_directory_already_exists"
expected_commit="$(tr -d '\r\n' < "$EXPECTED_COMMIT_FILE")"
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || die "expected_commit_invalid"

git bundle verify "$BUNDLE" >/dev/null || die "bundle_verify_failed"
bundle_head="$(git bundle list-heads "$BUNDLE" "refs/heads/$BRANCH")"
[[ "$bundle_head" == "$expected_commit refs/heads/$BRANCH" ]] || die "bundle_ref_mismatch"
git clone --branch "$BRANCH" --single-branch "$BUNDLE" "$TARGET" >/dev/null 2>&1 \
    || die "bundle_clone_failed"
server_head="$(git -C "$TARGET" rev-parse HEAD)"
[[ "$server_head" == "$expected_commit" ]] || die "server_head_mismatch"
status="$(git -C "$TARGET" -c core.excludesFile= status --porcelain=v1 --untracked-files=all)"
[[ -z "$status" ]] || die "server_clone_not_clean"

bash "$TARGET/scripts/phase8_pilot_server_run.sh" "$EXPECTED_COMMIT_FILE"
