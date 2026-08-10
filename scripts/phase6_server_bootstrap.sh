#!/usr/bin/env bash
set -Eeuo pipefail

readonly BUNDLE_PATH="/root/EasyUUV-phase6-v2.bundle"
readonly EXPECTED_COMMIT_FILE="/root/expected-source-commit.txt"
readonly TARGET_ROOT="/root/EASYkoopman-phase6-v2"
readonly BRANCH="v2.0-multi-configuration"

die() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

[[ -f "$BUNDLE_PATH" ]] || die "bundle_missing"
[[ -f "$EXPECTED_COMMIT_FILE" ]] || die "expected_commit_sidecar_missing"
[[ ! -e "$TARGET_ROOT" ]] || die "target_directory_already_exists"

expected_commit="$(tr -d '\r\n' < "$EXPECTED_COMMIT_FILE")"
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || die "expected_commit_invalid"

git bundle verify "$BUNDLE_PATH"
bundle_head="$(git bundle list-heads "$BUNDLE_PATH" "refs/heads/$BRANCH")"
read -r bundle_commit bundle_ref extra <<< "$bundle_head"
[[ -z "${extra:-}" ]] || die "bundle_ref_mismatch"
[[ "$bundle_commit" == "$expected_commit" ]] || die "bundle_ref_mismatch"
[[ "$bundle_ref" == "refs/heads/$BRANCH" ]] || die "bundle_ref_mismatch"

git clone --branch "$BRANCH" --single-branch "$BUNDLE_PATH" "$TARGET_ROOT"
server_head="$(git -C "$TARGET_ROOT" rev-parse HEAD)"
[[ "$server_head" == "$expected_commit" ]] || die "server_head_mismatch"
server_status="$(git -C "$TARGET_ROOT" status --porcelain)"
[[ -z "$server_status" ]] || die "server_clone_not_clean"

exec bash "$TARGET_ROOT/scripts/phase6_server_qualification.sh" \
    "$EXPECTED_COMMIT_FILE"
