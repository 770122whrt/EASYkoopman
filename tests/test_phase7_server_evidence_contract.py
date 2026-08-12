from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

from koopman.schema_v2 import validate_episode_artifact_v2
from workflows.collect_koopman_v2_smoke import (
    MINIMUM_TRANSITIONS,
    TOPOLOGY_CONFIGURATIONS,
    build_argument_parser as build_collect_parser,
    collect_episode_with_bridge,
    deterministic_action,
    resolve_output_path,
)
from workflows.merge_koopman_v2_evidence import (
    AGGREGATE_SCHEMA_VERSION,
    merge_koopman_v2_evidence,
    validate_aggregate_evidence,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "koopman_v2_three_topologies"
VALIDATOR = PROJECT_ROOT / "workflows" / "validate_koopman_v2.py"
COLLECTOR = PROJECT_ROOT / "workflows" / "collect_koopman_v2_smoke.py"
LOCAL_PREFLIGHT = PROJECT_ROOT / "scripts" / "phase7_local_preflight.ps1"
PREPARE_BUNDLE = PROJECT_ROOT / "scripts" / "phase7_prepare_bundle.ps1"
SERVER_BOOTSTRAP = PROJECT_ROOT / "scripts" / "phase7_server_bootstrap.sh"
SERVER_SMOKE = PROJECT_ROOT / "scripts" / "phase7_server_smoke.sh"
PULLBACK = PROJECT_ROOT / "scripts" / "phase7_pullback.ps1"
RUNBOOK = PROJECT_ROOT / "docs" / "phase7_koopman_v2_runbook.md"
SOURCE_COMMIT = "a" * 40
EXPECTED_CONFIGURATIONS = ("base", "uuv6", "uuv4")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_local_artifacts(tmp_path: Path) -> tuple[list[Path], dict[str, Path]]:
    manifests: list[Path] = []
    logs: dict[str, Path] = {}
    for configuration in EXPECTED_CONFIGURATIONS:
        jsonl = tmp_path / f"{configuration}.jsonl"
        manifest = tmp_path / f"{configuration}.manifest.json"
        log = tmp_path / f"{configuration}.log"
        jsonl.write_bytes((FIXTURE_ROOT / f"{configuration}.jsonl").read_bytes())
        manifest.write_bytes(
            (FIXTURE_ROOT / f"{configuration}.manifest.json").read_bytes()
        )
        original = [
            json.loads(line)
            for line in jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        records = [deepcopy(original[0])]
        for step in range(1, MINIMUM_TRANSITIONS):
            record = deepcopy(original[1])
            record["state_11"] = deepcopy(records[-1]["next_state_11"])
            record["next_state_11"] = deepcopy(record["state_11"])
            record["episode_provenance"]["step_index"] = step
            record["episode_provenance"]["simulation_time_s"] = 0.02 * step
            records.append(record)
        jsonl.write_text(
            "".join(
                json.dumps(row, allow_nan=False, separators=(",", ":"), sort_keys=True)
                + "\n"
                for row in records
            ),
            encoding="utf-8",
            newline="",
        )
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["transition_sha256"] = _sha256(jsonl)
        payload["record_count"] = MINIMUM_TRANSITIONS
        payload["last_step_index"] = MINIMUM_TRANSITIONS - 1
        payload["last_simulation_time_s"] = 0.02 * (MINIMUM_TRANSITIONS - 1)
        manifest.write_text(
            json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)
            + "\n",
            encoding="utf-8",
            newline="",
        )
        log.write_text(f"configuration={configuration}\nsemantic_status=pass\n", encoding="utf-8")
        manifests.append(manifest)
        logs[configuration] = log
    return manifests, logs


def _promote_fixture_to_server(
    manifest_path: Path,
    *,
    source_commit: str = SOURCE_COMMIT,
    actual_isaac_sim: str = "5.0.0",
    actual_isaac_lab: str = "2.2.1",
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    transition_path = manifest_path.with_name(manifest["transition_file"])
    records = [
        json.loads(line)
        for line in transition_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in records:
        record["episode_provenance"]["evidence_level"] = "server_isaac_smoke"
        record["episode_provenance"]["source_commit"] = source_commit
    transition_path.write_text(
        "".join(
            json.dumps(record, allow_nan=False, separators=(",", ":"), sort_keys=True)
            + "\n"
            for record in records
        ),
        encoding="utf-8",
        newline="",
    )
    manifest["episode_invariants"]["evidence_level"] = "server_isaac_smoke"
    manifest["episode_invariants"]["source_commit"] = source_commit
    manifest["evidence_level"] = "server_isaac_smoke"
    manifest["transition_sha256"] = _sha256(transition_path)
    manifest["runtime_provenance"] = {
        "artifact_origin": "server_isaac_smoke",
        "actual_isaac_sim": actual_isaac_sim,
        "actual_isaac_lab": actual_isaac_lab,
        "isaac_lab_release_tag": "v2.2.1",
        "isaac_lab_release_commit": "b" * 40,
        "isaac_lab_repo_commit": "b" * 40,
        "native_status": 0,
        "tee_status": 0,
        "semantic_status": "pass",
        "wrench_source": "post_actuator_thruster_only",
        "context_source": "same_step_oracle_snapshot",
    }
    manifest_path.write_text(
        json.dumps(manifest, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="",
    )
    validate_episode_artifact_v2(transition_path, manifest_path)


def _server_inputs(tmp_path: Path) -> tuple[list[Path], dict[str, Path]]:
    manifests, logs = _copy_local_artifacts(tmp_path)
    for manifest in manifests:
        _promote_fixture_to_server(manifest)
    return manifests, logs


def _parser_args(parser: argparse.ArgumentParser, *extra: str) -> argparse.Namespace:
    return parser.parse_args(
        [
            "--configuration",
            "base",
            "--task",
            "EasyUUV-Direct-v1",
            "--scenario",
            "phase7-smoke",
            "--episode-id",
            "phase7-base-001",
            "--seed",
            "7",
            "--result-root",
            "results",
            "--output-jsonl",
            "results/base.jsonl",
            "--output-manifest",
            "results/base.manifest.json",
            "--failure-json",
            "results/base.failure.json",
            "--headless",
            *extra,
        ]
    )


def test_collect_parser_is_isaac_free_and_exact_three() -> None:
    assert TOPOLOGY_CONFIGURATIONS == EXPECTED_CONFIGURATIONS
    parser = build_collect_parser()
    args = _parser_args(parser)
    assert args.configuration == "base"
    assert args.steps == MINIMUM_TRANSITIONS == 8
    assert args.seed == 7
    assert args.task == "EasyUUV-Direct-v1"
    assert args.scenario == "phase7-smoke"
    assert args.episode_id == "phase7-base-001"
    assert args.headless is True
    assert {args.output_jsonl.name, args.output_manifest.name, args.failure_json.name} == {
        "base.jsonl",
        "base.manifest.json",
        "base.failure.json",
    }
    for invalid in ("uuv3", "uuv4_angled", "heavy_duty"):
        with pytest.raises(SystemExit):
            _parser_args(parser, "--configuration", invalid)


@pytest.mark.parametrize("steps", ["0", "-1", "7"])
def test_collect_parser_rejects_fewer_than_eight_steps(steps: str) -> None:
    with pytest.raises(SystemExit):
        _parser_args(build_collect_parser(), "--steps", steps)


def test_collect_help_works_without_isaac_imports() -> None:
    code = (
        "import sys; import workflows.collect_koopman_v2_smoke as m; "
        "assert not any(x in sys.modules for x in ('torch','gymnasium','omni','isaaclab')); "
        "m.build_argument_parser().print_help()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for required in (
        "--configuration",
        "--steps",
        "--seed",
        "--task",
        "--scenario",
        "--episode-id",
        "--result-root",
        "--output-jsonl",
        "--output-manifest",
        "--failure-json",
        "--headless",
    ):
        assert required in result.stdout


def test_applauncher_precedes_gym_torch_and_environment_imports() -> None:
    source = COLLECTOR.read_text(encoding="utf-8")
    app = source.index("from isaaclab_app import AppLauncher")
    launch = source.index("AppLauncher(", app)
    assert launch < source.index("import gymnasium", launch)
    assert launch < source.index("import torch", launch)
    assert launch < source.index("easyuuv_nc", launch)


def test_deterministic_actions_exercise_all_channels_and_raw_uuv4_yaw() -> None:
    for configuration in EXPECTED_CONFIGURATIONS:
        actions = [deterministic_action(step, configuration) for step in range(8)]
        assert all(len(action) == 4 for action in actions)
        assert all(-1.0 <= value <= 1.0 for action in actions for value in action)
        assert all(any(action[channel] != 0.0 for action in actions) for channel in range(4))
    assert any(deterministic_action(step, "uuv4")[2] != 0.0 for step in range(8))


class _FakeBridge:
    def __init__(self, configuration: str, *, fail_at: int | None = None) -> None:
        self.configuration = configuration
        self.fail_at = fail_at
        self.actions: list[tuple[float, ...]] = []

    def step_and_record(self, action: tuple[float, ...], **_: object) -> dict:
        index = len(self.actions)
        self.actions.append(action)
        if self.fail_at == index:
            raise RuntimeError("bridge_telemetry_stale")
        virtual = list(action)
        if self.configuration == "uuv4":
            virtual[2] = 0.0
        return {
            "raw_action_4": list(action),
            "virtual_control_4": virtual,
            "episode_provenance": {"step_index": index},
        }


class _RecordingLogger:
    def __init__(self, *, finalize_error: Exception | None = None) -> None:
        self.records: list[dict] = []
        self.finalize_error = finalize_error
        self.finalized = False

    def write(self, record: dict) -> None:
        self.records.append(deepcopy(record))

    def finalize(self, **_: object) -> dict:
        if self.finalize_error is not None:
            raise self.finalize_error
        self.finalized = True
        return {"record_count": len(self.records), "evidence_level": "local_contract"}


def test_collection_calls_bridge_exactly_n_times_and_proves_uuv4_yaw_mask() -> None:
    bridge = _FakeBridge("uuv4")
    logger = _RecordingLogger()
    result = collect_episode_with_bridge(
        bridge=bridge,
        logger=logger,
        configuration="uuv4",
        steps=8,
        provenance={"evidence_level": "local_contract"},
    )
    assert result["record_count"] == 8
    assert logger.finalized is True
    yaw_rows = [row for row in logger.records if row["raw_action_4"][2] != 0.0]
    assert yaw_rows
    assert all(row["virtual_control_4"][2] == 0.0 for row in yaw_rows)


@pytest.mark.parametrize("failure", ["bridge", "finalize"])
def test_collection_fails_without_eligible_manifest_on_stale_or_invalid_data(
    failure: str,
) -> None:
    bridge = _FakeBridge("base", fail_at=2 if failure == "bridge" else None)
    logger = _RecordingLogger(
        finalize_error=ValueError("step_discontinuity") if failure == "finalize" else None
    )
    with pytest.raises((RuntimeError, ValueError)):
        collect_episode_with_bridge(
            bridge=bridge,
            logger=logger,
            configuration="base",
            steps=8,
            provenance={"evidence_level": "local_contract"},
        )
    assert logger.finalized is False


def test_output_path_is_confined_rechecked_and_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "results"
    valid = root / "base" / "episode.jsonl"
    assert resolve_output_path(valid, root) == valid.resolve()
    with pytest.raises(ValueError, match="output_outside_result_root"):
        resolve_output_path(tmp_path / "escape.jsonl", root)
    valid.parent.mkdir(parents=True, exist_ok=True)
    valid.write_text("old", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact_exists"):
        resolve_output_path(valid, root)


def test_output_path_rejects_symlink_components(tmp_path: Path) -> None:
    root = tmp_path / "results"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="output_symlink_component"):
        resolve_output_path(link / "episode.jsonl", root)


def test_local_exact_three_merge_remains_local_contract(tmp_path: Path) -> None:
    manifests, logs = _copy_local_artifacts(tmp_path)
    output = tmp_path / "evidence.json"
    aggregate = merge_koopman_v2_evidence(manifests, logs, output)
    assert output.is_file()
    assert aggregate["aggregate_version"] == AGGREGATE_SCHEMA_VERSION
    assert aggregate["evidence_level"] == "local_contract"
    assert [item["configuration"] for item in aggregate["episodes"]] == list(
        EXPECTED_CONFIGURATIONS
    )
    with pytest.raises(ValueError, match="server_evidence_required"):
        validate_aggregate_evidence(output, require_server=True)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra"])
def test_merge_requires_exact_three_unique_topologies(
    tmp_path: Path, mutation: str
) -> None:
    manifests, logs = _copy_local_artifacts(tmp_path)
    if mutation == "missing":
        manifests.pop()
    elif mutation == "duplicate":
        manifests[-1] = manifests[0]
    else:
        extra = tmp_path / "extra.manifest.json"
        extra.write_bytes(manifests[0].read_bytes())
        payload = json.loads(extra.read_text(encoding="utf-8"))
        payload["episode_invariants"]["configuration"] = "uuv4_angled"
        extra.write_text(json.dumps(payload), encoding="utf-8")
        manifests.append(extra)
    output = tmp_path / "evidence.json"
    with pytest.raises(ValueError, match="configuration_set_mismatch|duplicate_configuration"):
        merge_koopman_v2_evidence(manifests, logs, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("source", "metadata_disagreement"),
        ("runtime", "runtime_provenance_disagreement"),
        ("log", "log_missing"),
        ("hash", "manifest_hash_mismatch"),
    ],
)
def test_merge_rejects_source_runtime_log_and_hash_disagreement(
    tmp_path: Path, mutation: str, reason: str
) -> None:
    manifests, logs = _server_inputs(tmp_path)
    if mutation in {"source", "runtime"}:
        target = manifests[-1]
        payload = json.loads(target.read_text(encoding="utf-8"))
        if mutation == "source":
            payload["episode_invariants"]["source_commit"] = "c" * 40
        else:
            payload["runtime_provenance"]["actual_isaac_lab"] = "9.9.9"
        target.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "log":
        logs["uuv4"].unlink()
    else:
        manifests[-1].write_text(manifests[-1].read_text(encoding="utf-8") + " ", encoding="utf-8")
    output = tmp_path / "evidence.json"
    with pytest.raises(ValueError, match=reason):
        merge_koopman_v2_evidence(manifests, logs, output, require_server=True)
    assert not output.exists()


def test_failed_merge_preserves_existing_output_bytes(tmp_path: Path) -> None:
    manifests, logs = _copy_local_artifacts(tmp_path)
    output = tmp_path / "evidence.json"
    output.write_bytes(b"do-not-replace\n")
    manifests.pop()
    with pytest.raises(ValueError):
        merge_koopman_v2_evidence(manifests, logs, output)
    assert output.read_bytes() == b"do-not-replace\n"


def test_server_aggregate_revalidates_every_referenced_byte_and_hash(tmp_path: Path) -> None:
    manifests, logs = _server_inputs(tmp_path)
    output = tmp_path / "evidence.json"
    aggregate = merge_koopman_v2_evidence(
        manifests, logs, output, require_server=True
    )
    assert aggregate["evidence_level"] == "server_isaac_smoke"
    validated = validate_aggregate_evidence(output, require_server=True)
    assert validated["validation_gate"] == "koopman_v2_exact_three_server_evidence_valid"
    assert validated["configuration_count"] == 3
    (tmp_path / aggregate["episodes"][0]["episode_file"]).write_bytes(b"stale\n")
    with pytest.raises(ValueError, match="episode_hash_mismatch"):
        validate_aggregate_evidence(output, require_server=True)


@pytest.mark.parametrize("mutation", ["missing_ref", "extra_ref", "local_only"])
def test_aggregate_validator_rejects_partial_extra_or_local_only(
    tmp_path: Path, mutation: str
) -> None:
    if mutation == "local_only":
        manifests, logs = _copy_local_artifacts(tmp_path)
        output = tmp_path / "evidence.json"
        merge_koopman_v2_evidence(manifests, logs, output)
    else:
        manifests, logs = _server_inputs(tmp_path)
        output = tmp_path / "evidence.json"
        merge_koopman_v2_evidence(manifests, logs, output, require_server=True)
        payload = json.loads(output.read_text(encoding="utf-8"))
        if mutation == "missing_ref":
            payload["episodes"].pop()
        else:
            payload["episodes"].append(deepcopy(payload["episodes"][0]))
            payload["episodes"][-1]["configuration"] = "uuv4_angled"
        output.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="configuration_set_mismatch|server_evidence_required"):
        validate_aggregate_evidence(output, require_server=True)


def test_validator_cli_aggregate_mode_is_strict_and_json_reasoned(tmp_path: Path) -> None:
    manifests, logs = _server_inputs(tmp_path)
    output = tmp_path / "evidence.json"
    merge_koopman_v2_evidence(manifests, logs, output, require_server=True)
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--aggregate", str(output), "--json"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["validation_gate"] == "koopman_v2_exact_three_server_evidence_valid"
    output.write_text(output.read_text(encoding="utf-8").replace(SOURCE_COMMIT, "d" * 40), encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, str(VALIDATOR), "--aggregate", str(output), "--json"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert failed.returncode != 0
    assert "ERROR:" in failed.stderr


def _powershell() -> str:
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell unavailable")
    return executable


def _bash() -> str:
    executable = shutil.which("bash.exe") or shutil.which("bash")
    if executable is None:
        pytest.skip("Bash unavailable")
    return executable


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _git(cwd: Path, *args: str) -> str:
    result = _run(["git", *args], cwd=cwd)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _init_temp_repo(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-b", "v2.0-multi-configuration")
    _git(repository, "config", "user.email", "phase7@example.invalid")
    _git(repository, "config", "user.name", "Phase 7 Contract")
    (repository / "scripts").mkdir()
    return repository


def _commit_all(repository: Path, message: str) -> str:
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", message)
    return _git(repository, "rev-parse", "HEAD")


def test_phase7_operational_artifacts_exist_and_parse_in_native_shells() -> None:
    for path in (
        LOCAL_PREFLIGHT,
        PREPARE_BUNDLE,
        SERVER_BOOTSTRAP,
        SERVER_SMOKE,
        PULLBACK,
        RUNBOOK,
    ):
        assert path.is_file(), f"missing planned operational artifact: {path}"
    for script in (SERVER_BOOTSTRAP, SERVER_SMOKE):
        result = _run([_bash(), "-n", str(script)], cwd=PROJECT_ROOT)
        assert result.returncode == 0, result.stderr
    parser = (
        "$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile("
        "$args[0],[ref]$null,[ref]$errors) > $null; "
        "if($errors.Count){$errors | ForEach-Object {Write-Error $_}; exit 1}"
    )
    for script in (LOCAL_PREFLIGHT, PREPARE_BUNDLE, PULLBACK):
        result = _run(
            [_powershell(), "-NoProfile", "-Command", parser, str(script)],
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "required_gate",
    [
        "targeted_phase7_tests",
        "full_collect_only",
        "full_pytest",
        "compileall",
        "pip_check",
        "bash_parse",
        "powershell_parse",
        "git_diff_check",
        "protected_diff",
        "worktree_clean",
        "canonical_evidence_absent",
    ],
)
def test_local_preflight_declares_every_fail_closed_gate(required_gate: str) -> None:
    source = LOCAL_PREFLIGHT.read_text(encoding="utf-8")
    assert required_gate in source
    assert "exit 1" in source
    assert "source/results/koopman_phase7" in source
    assert "--untracked-files=all" in source
    assert ".pytest-tmp/phase7-full-suite" in source


def test_prepare_invokes_same_preflight_before_any_bundle_command() -> None:
    source = PREPARE_BUNDLE.read_text(encoding="utf-8")
    preflight = source.index("phase7_local_preflight.ps1")
    bundle_create = source.index("bundle create")
    assert preflight < bundle_create
    assert "worktree_dirty" in source
    assert "--untracked-files=all" in source
    assert "bundle verify" in source
    assert "bundle list-heads" in source
    assert "expected-source-commit.txt" in source


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_prepare_dynamic_dirty_repo_stops_before_transfer(
    tmp_path: Path, dirty_kind: str
) -> None:
    repository = _init_temp_repo(tmp_path)
    shutil.copy2(PREPARE_BUNDLE, repository / "scripts" / PREPARE_BUNDLE.name)
    shutil.copy2(LOCAL_PREFLIGHT, repository / "scripts" / LOCAL_PREFLIGHT.name)
    (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _commit_all(repository, "fixture")
    if dirty_kind == "tracked":
        (repository / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    else:
        (repository / "unignored.txt").write_text("dirty\n", encoding="utf-8")
    result = _run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repository / "scripts" / PREPARE_BUNDLE.name),
            "-RepositoryRoot",
            str(repository),
            "-TransferDirectory",
            "transfer",
        ],
        cwd=repository,
    )
    assert result.returncode != 0
    assert "worktree_dirty" in result.stderr + result.stdout
    assert not (repository / "transfer").exists()


def test_prepare_dynamic_preflight_failure_stops_before_bundle(tmp_path: Path) -> None:
    repository = _init_temp_repo(tmp_path)
    shutil.copy2(PREPARE_BUNDLE, repository / "scripts" / PREPARE_BUNDLE.name)
    (repository / "scripts" / LOCAL_PREFLIGHT.name).write_text(
        "Write-Error 'targeted_phase7_tests_failed'; exit 17\n", encoding="utf-8"
    )
    _commit_all(repository, "fixture")
    result = _run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repository / "scripts" / PREPARE_BUNDLE.name),
            "-RepositoryRoot",
            str(repository),
            "-TransferDirectory",
            "transfer",
        ],
        cwd=repository,
    )
    assert result.returncode != 0
    assert "local_preflight_failed" in result.stderr + result.stdout
    assert not (repository / "transfer").exists()


def test_server_bootstrap_binds_complete_bundle_sidecar_clean_head_and_fresh_target() -> None:
    source = SERVER_BOOTSTRAP.read_text(encoding="utf-8")
    for required in (
        "set -Eeuo pipefail",
        "/root/EasyUUV-phase7-v2.bundle",
        "/root/expected-source-commit.txt",
        "/root/EASYkoopman-phase7-v2",
        "target_directory_already_exists",
        "bundle verify",
        "bundle list-heads",
        "server_head_mismatch",
        "server_clone_not_clean",
        "--untracked-files=all",
    ):
        assert required in source


def test_server_smoke_locks_offline_runtime_three_process_and_pipeline_gates() -> None:
    source = SERVER_SMOKE.read_text(encoding="utf-8")
    for required in (
        "set -Eeuo pipefail",
        "PYTHONDONTWRITEBYTECODE=1",
        "/root/IsaacLab/isaaclab.sh",
        '"$ISAACLAB_PY" -p',
        "5.0",
        "2.2.1",
        "setuptools",
        "--no-deps",
        "--no-build-isolation",
        "--no-index",
        "PIPESTATUS",
        "native_status",
        "tee_status",
        "semantic_status",
        "run_one base",
        "run_one uuv6",
        "run_one uuv4",
        "runner_failure_blocks_merge",
        "merge_koopman_v2_evidence.py",
        "validate_koopman_v2.py",
        "sha256sum",
    ):
        assert required in source
    assert source.index("runner_failure_blocks_merge") < source.index(
        "merge_koopman_v2_evidence.py"
    )
    assert "pip install -e" in source
    assert "--no-index" in source
    assert "__pycache__" in source and "bytecode_pollution" in source


def test_pullback_orders_scp_hash_source_runtime_validator_before_promotion() -> None:
    source = PULLBACK.read_text(encoding="utf-8")
    for required in (
        "phase7-pullback-",
        "scp_failed",
        "sha256_mismatch",
        "source_commit_mismatch",
        "isaaclab_release_tag",
        "isaaclab_release_commit",
        "isaaclab_repo_commit",
        "runtime_version_mismatch",
        "worktree_dirty",
        "--untracked-files=all",
        "workflows/validate_koopman_v2.py",
        "--aggregate",
        "validator_failed",
        "canonical_evidence_already_exists",
        "Move-Item",
    ):
        assert required in source
    assert source.index("scp") < source.index("sha256_mismatch")
    assert source.index("sha256_mismatch") < source.index("source_commit_mismatch")
    assert source.index("source_commit_mismatch") < source.index("--aggregate")
    assert source.index("--aggregate") < source.index("Move-Item")


def test_runbook_has_exact_operator_sequence_and_claim_boundary() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for heading in (
        "## Evidence Levels",
        "## Local Preflight",
        "## Offline Bundle",
        "## Server Bootstrap",
        "## Server Three-Topology Smoke",
        "## Merge/Validate/Hash",
        "## Pullback",
        "## Failure Handling",
        "## Claim Boundary",
    ):
        assert heading in text
    for required in (
        "base",
        "uuv6",
        "uuv4",
        "8 transitions",
        "/root/EASYkoopman-phase7-v2",
        "agent connects",
        "schema/Bridge integration",
        "does not prove Koopman effect",
    ):
        assert required in text
