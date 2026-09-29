#!/usr/bin/env bash
set -Eeuo pipefail

readonly TRANSFER_ROOT="${TRANSFER_ROOT:-/root}"
readonly PROJECT_ROOT="/root/EASYkoopman-phase8-2-v2"
readonly SERVER_RESULT_ROOT="/root/EASYkoopman-phase8-2-results-v2"
readonly BUNDLE="$TRANSFER_ROOT/EasyUUV-phase8-2-v2.bundle"
readonly EXPECTED_COMMIT_FILE="$TRANSFER_ROOT/expected-source-commit.txt"
readonly EXPECTED_BRANCH_FILE="$TRANSFER_ROOT/expected-branch.txt"
readonly EXPECTED_BUNDLE_HASH_FILE="$TRANSFER_ROOT/bundle.sha256"

die() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

for path in "$BUNDLE" "$EXPECTED_COMMIT_FILE" "$EXPECTED_BRANCH_FILE" \
    "$EXPECTED_BUNDLE_HASH_FILE" "$TRANSFER_ROOT/role-protocol.sha256" \
    "$TRANSFER_ROOT/analysis-policy.sha256" "$TRANSFER_ROOT/d23-approval.sha256"; do
    [[ -f "$path" ]] || die "bundle_sidecar_missing:$path"
done
[[ ! -e "$PROJECT_ROOT" ]] || die "isolated_project_root_exists"
[[ ! -e "$SERVER_RESULT_ROOT" ]] || die "isolated_result_root_exists"

expected_commit="$(tr -d '\r\n' < "$EXPECTED_COMMIT_FILE")"
expected_branch="$(tr -d '\r\n' < "$EXPECTED_BRANCH_FILE")"
expected_bundle_hash="$(tr -d '\r\n' < "$EXPECTED_BUNDLE_HASH_FILE")"
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || die "expected_source_commit_invalid"
[[ -n "$expected_branch" ]] || die "expected_branch_invalid"
[[ "$(sha256sum "$BUNDLE" | awk '{print $1}')" == "$expected_bundle_hash" ]] \
    || die "bundle_sha256_mismatch"

verify_repository="$(mktemp -d "${TMPDIR:-/tmp}/phase8-2-bundle-verify.XXXXXX")"
trap 'rm -rf -- "$verify_repository"' EXIT
git init --bare "$verify_repository" >/dev/null || die "bundle_verify_repository_init_failed"
git -C "$verify_repository" bundle verify "$BUNDLE" >/dev/null || die "bundle_verify_failed"
bundle_head="$(git bundle list-heads "$BUNDLE" "refs/heads/$expected_branch")"
[[ "$bundle_head" == "$expected_commit refs/heads/$expected_branch" ]] || die "bundle_ref_mismatch"

git clone "$BUNDLE" "$PROJECT_ROOT" >/dev/null || die "git_clone_failed"
git -C "$PROJECT_ROOT" checkout --detach "$expected_commit" >/dev/null || die "checkout_failed"
[[ "$(git -C "$PROJECT_ROOT" rev-parse HEAD)" == "$expected_commit" ]] || die "source_commit_mismatch"
[[ -z "$(git -C "$PROJECT_ROOT" -c core.excludesFile= status --porcelain=v1 --untracked-files=all)" ]] \
    || die "worktree_dirty"

for binding in \
    "protocols/phase8_1/main_role_assignment_protocol.json:role-protocol.sha256" \
    "protocols/phase8_1/analysis_policy.json:analysis-policy.sha256" \
    "protocols/phase8_1/d23_approval.json:d23-approval.sha256"; do
    relative="${binding%%:*}"
    sidecar="${binding##*:}"
    expected="$(tr -d '\r\n' < "$TRANSFER_ROOT/$sidecar")"
    actual="$(sha256sum "$PROJECT_ROOT/$relative" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || die "protocol_binding_mismatch:$relative"
done

RESULT_ROOT="$SERVER_RESULT_ROOT" bash "$PROJECT_ROOT/scripts/phase8_2_server_collect.sh"
