"""Contracts for the exact-policy Phase 8 collector and pilot server chain."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from koopman.protocol_v2 import (
    PILOT_RAW_ACTION_ABS_MAX,
    PUBLIC_CONFIGURATIONS,
    load_pilot_collection_policy,
)
import workflows.collect_koopman_v2_identification as collector
from workflows.collect_koopman_v2_identification import (
    build_argument_parser,
    collect_policy_entries,
    deterministic_policy_action,
    resolve_output_path,
    write_episode_success_logs,
)
from workflows.audit_koopman_v2_pilot import audit_pilot_collection
from test_phase8_protocol_evidence import (
    _canonical_bytes as _fixture_canonical_bytes,
    _write_fixture as _write_evidence_fixture,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "protocols" / "phase8" / "pilot_collection_policy.json"
COLLECTOR = PROJECT_ROOT / "workflows" / "collect_koopman_v2_identification.py"
LOCAL_PREFLIGHT = PROJECT_ROOT / "scripts" / "phase8_pilot_local_preflight.ps1"
PREPARE_BUNDLE = PROJECT_ROOT / "scripts" / "phase8_pilot_prepare_bundle.ps1"
SERVER_BOOTSTRAP = PROJECT_ROOT / "scripts" / "phase8_pilot_server_bootstrap.sh"
SERVER_RUN = PROJECT_ROOT / "scripts" / "phase8_pilot_server_run.sh"
PULLBACK = PROJECT_ROOT / "scripts" / "phase8_pilot_pullback.ps1"
RUNBOOK = PROJECT_ROOT / "docs" / "phase8_koopman_identification_runbook.md"
EXPECTED_CONFIGURATIONS = (
    "base",
    "long_body",
    "heavy_moderate",
    "asymmetric",
    "uuv6",
    "uuv6_angled",
    "uuv4",
    "uuv4_angled",
)


def _powershell() -> str:
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell unavailable")
    return executable


def _bash() -> str:
    if os.name == "nt":
        result = subprocess.run(
            ["git", "--exec-path"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        exec_path = Path(result.stdout.strip()).resolve()
        candidate = exec_path.parents[2] / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
        pytest.skip("Git Bash unavailable")
    executable = shutil.which("bash")
    if executable is None:
        pytest.skip("Bash unavailable")
    return executable


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
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
    _git(repository, "config", "user.email", "phase8@example.invalid")
    _git(repository, "config", "user.name", "Phase 8 Contract")
    (repository / "scripts").mkdir()
    return repository


def _commit_all(repository: Path, message: str) -> str:
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", message)
    return _git(repository, "rev-parse", "HEAD")


def _write_exact_inventory(evidence: Path, status: Path) -> None:
    lines = []
    for path in sorted(item for item in evidence.rglob("*") if item.is_file()):
        relative = path.relative_to(evidence).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  ./{relative}\n")
    (status / "all_files.sha256").write_text("".join(lines), encoding="utf-8")


def _rewrite_fixture_source_commit(evidence: Path, source_commit: str) -> None:
    for episode in sorted((evidence / "episodes").glob("*.jsonl")):
        rows = [json.loads(line) for line in episode.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            row["episode_provenance"]["source_commit"] = source_commit
        episode.write_bytes(b"".join(_fixture_canonical_bytes(row) for row in rows))
        manifest = evidence / "manifests" / f"{episode.stem}.manifest.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["transition_sha256"] = hashlib.sha256(episode.read_bytes()).hexdigest()
        payload["episode_invariants"]["source_commit"] = source_commit
        manifest.write_bytes(_fixture_canonical_bytes(payload))


def _write_fake_scp(directory: Path) -> None:
    directory.mkdir()
    if os.name == "nt":
        (directory / "scp.cmd").write_text(
            "@echo off\n"
            "if \"%PHASE8_FAKE_SCP_FAIL%\"==\"1\" exit /b 23\n"
            "echo %~2 | findstr /C:\"status\" >nul\n"
            "if errorlevel 1 (\n"
            "  robocopy \"%PHASE8_FAKE_EVIDENCE%\" \"%~3\\koopman_phase8_pilot\" /E /NFL /NDL /NJH /NJS >nul\n"
            ") else (\n"
            "  robocopy \"%PHASE8_FAKE_STATUS%\" \"%~3\\koopman_phase8_pilot_status\" /E /NFL /NDL /NJH /NJS >nul\n"
            ")\n"
            "if %ERRORLEVEL% LSS 8 exit /b 0\n"
            "exit /b %ERRORLEVEL%\n",
            encoding="utf-8",
        )
    else:
        script = directory / "scp"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "[[ ${PHASE8_FAKE_SCP_FAIL:-0} != 1 ]] || exit 23\n"
            "source=$PHASE8_FAKE_EVIDENCE\n"
            "leaf=koopman_phase8_pilot\n"
            "[[ $2 != *status* ]] || { source=$PHASE8_FAKE_STATUS; leaf=koopman_phase8_pilot_status; }\n"
            "cp -R \"$source\" \"$3/$leaf\"\n",
            encoding="utf-8",
        )
        script.chmod(0o755)


def _pullback_fixture(tmp_path: Path, *, canonical_exists: bool = False) -> tuple[Path, Path, Path, str]:
    repository = _init_temp_repo(tmp_path)
    (repository / "workflows").mkdir()
    (repository / "koopman").mkdir()
    (repository / "source" / "results").mkdir(parents=True)
    shutil.copy2(PULLBACK, repository / "scripts" / PULLBACK.name)
    shutil.copy2(
        PROJECT_ROOT / "workflows" / "validate_phase8_evidence.py",
        repository / "workflows" / "validate_phase8_evidence.py",
    )
    shutil.copy2(
        PROJECT_ROOT / "workflows" / "validate_phase8_pilot_policy.py",
        repository / "workflows" / "validate_phase8_pilot_policy.py",
    )
    shutil.copy2(
        PROJECT_ROOT / "koopman" / "evidence_v2.py",
        repository / "koopman" / "evidence_v2.py",
    )
    shutil.copy2(
        PROJECT_ROOT / "koopman" / "protocol_v2.py",
        repository / "koopman" / "protocol_v2.py",
    )
    (repository / "koopman" / "__init__.py").write_text("", encoding="utf-8")
    (repository / ".gitignore").write_text(".pytest-tmp/\n", encoding="utf-8")
    if canonical_exists:
        canonical = repository / "source" / "results" / "koopman_phase8_pilot"
        canonical.mkdir()
        (canonical / "sentinel.txt").write_text("keep\n", encoding="utf-8")
    source_commit = _commit_all(repository, "pullback fixture")
    transfer = repository / ".pytest-tmp" / "phase8-pilot-transfer"
    transfer.mkdir(parents=True)
    (transfer / "expected-source-commit.txt").write_text(
        f"{source_commit}\n", encoding="utf-8"
    )

    evidence = tmp_path / "remote" / "koopman_phase8_pilot"
    evidence.parent.mkdir()
    _write_evidence_fixture(evidence)
    _rewrite_fixture_source_commit(evidence, source_commit)
    audit_pilot_collection(evidence, require_server=True)

    status = tmp_path / "remote" / "koopman_phase8_pilot_status"
    status.mkdir()
    for configuration in EXPECTED_CONFIGURATIONS:
        (status / f"{configuration}.native_status").write_text("0\n", encoding="utf-8")
        (status / f"{configuration}.tee_status").write_text("0\n", encoding="utf-8")
        (status / f"{configuration}.semantic_status").write_text("pass\n", encoding="utf-8")
    sidecars = {
        "source_commit.txt": source_commit,
        "isaac_sim_version.txt": "5.0",
        "isaaclab_version.txt": "2.2.1",
        "isaaclab_release_tag.txt": "v2.2.1",
        "isaaclab_release_commit.txt": "0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20",
        "isaaclab_repo_commit.txt": "c91a125c73c8b574878419a9583afc0b63b99f0a",
        "isaaclab_repo_parent_commit.txt": "0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20",
        "isaaclab_repo_patch.sha256": "d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079",
        "isaaclab_repo_dirty_files.txt": (
            "source/isaaclab_mimic/setup.py\nsource/isaaclab_rl/setup.py"
        ),
    }
    for name, value in sidecars.items():
        (status / name).write_bytes(f"{value}\n".encode("utf-8"))
    envelope = evidence / "pilot_envelope.json"
    envelope_hash = hashlib.sha256(envelope.read_bytes()).hexdigest()
    (status / "pilot_envelope.sha256").write_text(
        f"{envelope_hash}  {envelope.as_posix()}\n", encoding="utf-8"
    )
    _write_exact_inventory(evidence, status)
    return repository, evidence, status, source_commit


def test_collector_parser_is_policy_driven_and_has_no_episode_mutation_flags():
    parser = build_argument_parser()
    args = parser.parse_args(
        [
            "--policy",
            str(POLICY_PATH),
            "--configuration",
            "uuv4",
            "--result-root",
            "results",
            "--headless",
        ]
    )
    assert args.policy == POLICY_PATH
    assert args.configuration == "uuv4"
    assert args.result_root == Path("results")
    assert args.headless is True
    assert tuple(PUBLIC_CONFIGURATIONS) == EXPECTED_CONFIGURATIONS
    help_text = parser.format_help()
    for forbidden in (
        "--seed",
        "--steps",
        "--episode-id",
        "--scenario",
        "--task",
        "--controller-mode",
        "--role",
        "--model",
    ):
        assert forbidden not in help_text
    for invalid in ("unknown", "heavy_duty", "uuv3"):
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "--policy",
                    str(POLICY_PATH),
                    "--configuration",
                    invalid,
                    "--result-root",
                    "results",
                ]
            )


def test_policy_actions_are_deterministic_bounded_signed_and_seed_specific():
    policy = load_pilot_collection_policy(POLICY_PATH)
    by_kind = {entry["policy_kind"]: entry for entry in policy["entries"][:2]}
    for entry in by_kind.values():
        first = [deterministic_policy_action(entry, step) for step in range(128)]
        second = [deterministic_policy_action(deepcopy(entry), step) for step in range(128)]
        assert first == second
        assert all(len(action) == 4 for action in first)
        assert all(
            abs(value) <= PILOT_RAW_ACTION_ABS_MAX
            for action in first
            for value in action
        )
        for channel in range(4):
            assert any(action[channel] > 0.0 for action in first)
            assert any(action[channel] < 0.0 for action in first)
    assert [deterministic_policy_action(by_kind["axis_pulse"], step) for step in range(128)] != [
        deterministic_policy_action(by_kind["bounded_multisine"], step)
        for step in range(128)
    ]


def test_koopman_protocol_layer_contains_no_server_runtime_tokens():
    source = (PROJECT_ROOT / "koopman" / "protocol_v2.py").read_text(encoding="utf-8")

    assert "isaaclab" not in source.lower()
    assert "/root/" not in source


def test_operational_policy_owns_and_accepts_the_exact_server_runtime_contract():
    from workflows.validate_phase8_pilot_policy import (
        EXPECTED_SERVER_RUNTIME_CONTRACT,
        load_operational_pilot_policy,
    )

    policy = load_operational_pilot_policy(POLICY_PATH)

    assert policy["runtime_contract"] == EXPECTED_SERVER_RUNTIME_CONTRACT
    assert EXPECTED_SERVER_RUNTIME_CONTRACT == {
        "isaac_sim_version": "5.0",
        "isaac_lab_version": "2.2.1",
        "python_entrypoint": "/root/IsaacLab/isaaclab.sh -p",
    }


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("runtime_contract_missing", "pilot_policy_invalid"),
        ("python_entrypoint_missing", "pilot_policy_invalid"),
        ("python_entrypoint_drift", "pilot_runtime_contract_mismatch:python_entrypoint"),
        ("isaac_sim_version_drift", "pilot_runtime_contract_mismatch:isaac_sim_version"),
        ("isaac_lab_version_drift", "pilot_runtime_contract_mismatch:isaac_lab_version"),
    ],
)
def test_operational_policy_rejects_missing_or_drifted_runtime_contract(
    mutation: str, reason: str
):
    from workflows.validate_phase8_pilot_policy import validate_operational_pilot_policy

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if mutation == "runtime_contract_missing":
        policy.pop("runtime_contract")
    elif mutation == "python_entrypoint_missing":
        policy["runtime_contract"].pop("python_entrypoint")
    elif mutation == "python_entrypoint_drift":
        policy["runtime_contract"]["python_entrypoint"] = "/usr/bin/python3"
    elif mutation == "isaac_sim_version_drift":
        policy["runtime_contract"]["isaac_sim_version"] = "5.1"
    elif mutation == "isaac_lab_version_drift":
        policy["runtime_contract"]["isaac_lab_version"] = "2.3.0"

    with pytest.raises(ValueError, match=rf"^{reason}(?::|$)"):
        validate_operational_pilot_policy(policy)


def test_pilot_audit_revalidates_operational_runtime_before_writing_evidence(tmp_path: Path):
    root = tmp_path / "pilot"
    _write_evidence_fixture(root)
    policy_path = root / "pilot_collection_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["runtime_contract"]["python_entrypoint"] = "/usr/bin/python3"
    policy_path.write_bytes(_fixture_canonical_bytes(policy))

    with pytest.raises(
        ValueError,
        match=r"^pilot_runtime_contract_mismatch:python_entrypoint(?::|$)",
    ):
        audit_pilot_collection(root, require_server=True)
    assert not (root / "pilot_inventory.json").exists()
    assert not (root / "pilot_health_decision.json").exists()
    assert not (root / "pilot_envelope.json").exists()


class _FakeBridge:
    def __init__(self, entry: dict, *, fail_at: int | None = None) -> None:
        self.entry = entry
        self.fail_at = fail_at
        self.actions: list[tuple[float, ...]] = []

    def step_and_record(self, action: tuple[float, ...]) -> dict:
        step = len(self.actions)
        self.actions.append(action)
        if self.fail_at == step:
            raise RuntimeError("bridge_telemetry_stale")
        virtual = list(action)
        if self.entry["configuration"].startswith("uuv4"):
            virtual[2] = 0.0
        return {
            "raw_action_4": list(action),
            "virtual_control_4": virtual,
            "episode_provenance": {
                "episode_id": self.entry["episode_id"],
                "step_index": step,
            },
        }


class _FakeLogger:
    def __init__(self, entry: dict) -> None:
        self.entry = entry
        self.rows: list[dict] = []
        self.finalized = False

    def write(self, row: dict) -> None:
        self.rows.append(deepcopy(row))

    def finalize(self) -> dict:
        self.finalized = True
        return {"episode_id": self.entry["episode_id"], "record_count": len(self.rows)}


def test_collection_resets_and_finalizes_two_independent_policy_episodes():
    policy = load_pilot_collection_policy(POLICY_PATH)
    entries = [entry for entry in policy["entries"] if entry["configuration"] == "uuv4"]
    resets: list[tuple[int, str]] = []
    bridges: list[_FakeBridge] = []
    loggers: list[_FakeLogger] = []

    def reset(seed: int, episode_id: str) -> None:
        resets.append((seed, episode_id))

    def bridge_factory(entry: dict) -> _FakeBridge:
        bridge = _FakeBridge(entry)
        bridges.append(bridge)
        return bridge

    def logger_factory(entry: dict) -> _FakeLogger:
        logger = _FakeLogger(entry)
        loggers.append(logger)
        return logger

    result = collect_policy_entries(
        entries,
        reset=reset,
        bridge_factory=bridge_factory,
        logger_factory=logger_factory,
    )

    assert resets == [(entry["seed"], entry["episode_id"]) for entry in entries]
    assert len(bridges) == len(loggers) == 2
    assert all(len(bridge.actions) == 128 for bridge in bridges)
    assert all(logger.finalized and len(logger.rows) == 128 for logger in loggers)
    assert [item["episode_id"] for item in result] == [entry["episode_id"] for entry in entries]
    for logger in loggers:
        yaw_rows = [row for row in logger.rows if row["raw_action_4"][2] != 0.0]
        assert yaw_rows
        assert all(row["virtual_control_4"][2] == 0.0 for row in yaw_rows)


def test_collection_failure_never_finalizes_failed_or_later_episode():
    policy = load_pilot_collection_policy(POLICY_PATH)
    entries = [entry for entry in policy["entries"] if entry["configuration"] == "base"]
    loggers: list[_FakeLogger] = []

    def bridge_factory(entry: dict) -> _FakeBridge:
        return _FakeBridge(entry, fail_at=7 if len(loggers) == 0 else None)

    def logger_factory(entry: dict) -> _FakeLogger:
        logger = _FakeLogger(entry)
        loggers.append(logger)
        return logger

    with pytest.raises(RuntimeError, match="bridge_telemetry_stale"):
        collect_policy_entries(
            entries,
            reset=lambda seed, episode_id: None,
            bridge_factory=bridge_factory,
            logger_factory=logger_factory,
        )
    assert len(loggers) == 1
    assert loggers[0].finalized is False


def test_success_logs_are_one_fresh_log_per_policy_episode(tmp_path: Path):
    policy = load_pilot_collection_policy(POLICY_PATH)
    entries = [entry for entry in policy["entries"] if entry["configuration"] == "base"]
    root = tmp_path / "pilot"
    results = [
        {"episode_id": entry["episode_id"], "record_count": entry["transition_count"]}
        for entry in entries
    ]

    paths = write_episode_success_logs(root, entries, results)

    assert len(paths) == 2
    for entry, path in zip(entries, paths, strict=True):
        assert path == root / "logs" / f"{entry['episode_id']}.log"
        text = path.read_text(encoding="utf-8")
        assert f"episode_id={entry['episode_id']}" in text
        assert "semantic_status=pass" in text
        assert "record_count=128" in text
    with pytest.raises(ValueError, match="artifact_exists"):
        write_episode_success_logs(root, entries, results)


def test_output_paths_are_confined_fresh_and_noncolliding(tmp_path: Path):
    root = tmp_path / "pilot"
    episode = root / "episodes" / "episode.jsonl"
    assert resolve_output_path(episode, root) == episode.resolve()
    with pytest.raises(ValueError, match="output_outside_result_root"):
        resolve_output_path(tmp_path / "escape.jsonl", root)
    episode.parent.mkdir(parents=True, exist_ok=True)
    episode.write_text("old\n", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact_exists"):
        resolve_output_path(episode, root)


def test_collector_launches_app_before_runtime_imports_and_has_no_model_imports():
    source = COLLECTOR.read_text(encoding="utf-8")
    app = source.index("from isaaclab_app import AppLauncher")
    launch = source.index("AppLauncher(", app)
    assert launch < source.index("import gymnasium", launch)
    assert launch < source.index("import torch", launch)
    assert launch < source.index("easyuuv_nc", launch)
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    forbidden = ("koopman.model", "koopman.edmd", "koopman.evaluation", "koopman.loco_v2")
    assert not any(name == prefix or name.startswith(prefix + ".") for name in imports for prefix in forbidden)


def test_phase8_operational_artifacts_exist_and_parse_in_native_shells():
    for path in (
        LOCAL_PREFLIGHT,
        PREPARE_BUNDLE,
        SERVER_BOOTSTRAP,
        SERVER_RUN,
        PULLBACK,
        RUNBOOK,
    ):
        assert path.is_file(), f"missing planned operational artifact: {path}"
    for script in (SERVER_BOOTSTRAP, SERVER_RUN):
        result = _run([_bash(), "-n", script.relative_to(PROJECT_ROOT).as_posix()], cwd=PROJECT_ROOT)
        assert result.returncode == 0, result.stderr
        assert b"\r\n" not in script.read_bytes()
    parser = (
        "$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile("
        "$env:PHASE8_PARSE_TARGET,[ref]$null,[ref]$errors) > $null; "
        "if($errors.Count){$errors | ForEach-Object {Write-Error $_}; exit 1}"
    )
    for script in (LOCAL_PREFLIGHT, PREPARE_BUNDLE, PULLBACK):
        environment = dict(os.environ)
        environment["PHASE8_PARSE_TARGET"] = str(script)
        result = _run(
            [_powershell(), "-NoProfile", "-Command", parser],
            cwd=PROJECT_ROOT,
            env=environment,
        )
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "required_gate",
    [
        "targeted_phase8_tests",
        "full_collect_only",
        "full_pytest",
        "compileall",
        "pip_check",
        "bash_parse",
        "powershell_parse",
        "git_diff_check",
        "protected_diff",
        "worktree_clean",
        "canonical_pilot_absent",
    ],
)
def test_local_preflight_declares_every_fail_closed_gate(required_gate: str):
    source = LOCAL_PREFLIGHT.read_text(encoding="utf-8")
    assert required_gate in source
    assert "exit 1" in source
    assert "source/results/koopman_phase8_pilot" in source
    assert "--untracked-files=all" in source
    assert ".pytest-tmp/phase8-pilot-preflight-" in source
    assert "$phase8TempRoot/full-suite" in source
    assert "tests/test_phase8_protocol_evidence.py" in source
    assert "tests/test_phase8_pilot_server_contract.py" in source


def test_preflight_protects_v1_phase6_phase7_and_frozen_schema():
    source = LOCAL_PREFLIGHT.read_text(encoding="utf-8")
    assert "diff --name-only v1.0 --" in source
    for protected in (
        "koopman/model.py",
        "koopman/lifted_edmd.py",
        "koopman/mpc.py",
        "source/results/koopman_phase6",
        "source/results/koopman_phase7",
        "koopman/schema_v2.py",
    ):
        assert protected in source


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_prepare_dynamic_dirty_repo_stops_before_transfer(tmp_path: Path, dirty_kind: str):
    repository = _init_temp_repo(tmp_path)
    shutil.copy2(PREPARE_BUNDLE, repository / "scripts" / PREPARE_BUNDLE.name)
    shutil.copy2(LOCAL_PREFLIGHT, repository / "scripts" / LOCAL_PREFLIGHT.name)
    (repository / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _commit_all(repository, "fixture")
    if dirty_kind == "tracked":
        (repository / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    else:
        (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")
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
    assert "worktree_dirty" in result.stdout + result.stderr
    assert not (repository / "transfer").exists()


def test_prepare_dynamic_preflight_failure_stops_before_bundle(tmp_path: Path):
    repository = _init_temp_repo(tmp_path)
    shutil.copy2(PREPARE_BUNDLE, repository / "scripts" / PREPARE_BUNDLE.name)
    (repository / "scripts" / LOCAL_PREFLIGHT.name).write_text(
        "Write-Error 'targeted_phase8_tests_failed'; exit 17\n", encoding="utf-8"
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
    assert "local_preflight_failed" in result.stdout + result.stderr
    assert not (repository / "transfer").exists()


def test_prepare_binds_preflight_clean_head_bundle_and_sidecar():
    source = PREPARE_BUNDLE.read_text(encoding="utf-8")
    assert source.index("phase8_pilot_local_preflight.ps1") < source.index("bundle create")
    for required in (
        "worktree_dirty",
        "--untracked-files=all",
        "bundle verify",
        "bundle list-heads",
        "expected-source-commit.txt",
        "EasyUUV-phase8-pilot-v2.bundle",
        "tested_head_not_branch_tip",
        "canonical_evidence_already_exists",
    ):
        assert required in source


def test_server_bootstrap_binds_exact_bundle_head_fresh_isolated_target():
    source = SERVER_BOOTSTRAP.read_text(encoding="utf-8")
    for required in (
        "set -Eeuo pipefail",
        "/root/EasyUUV-phase8-pilot-v2.bundle",
        "/root/expected-source-commit.txt",
        "/root/EASYkoopman-phase8-pilot-v2",
        "target_directory_already_exists",
        "bundle verify",
        "bundle list-heads",
        "server_head_mismatch",
        "server_clone_not_clean",
        "phase8_pilot_server_run.sh",
    ):
        assert required in source


def test_server_run_locks_offline_runtime_exact_eight_and_process_statuses():
    source = SERVER_RUN.read_text(encoding="utf-8")
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
        "runner_failure_blocks_audit",
        "audit_koopman_v2_pilot.py",
        "validate_phase8_evidence.py",
        "server_isaac_identification_pilot",
        "validate_phase8_pilot_policy.py",
        "pilot_policy_hash_mismatch",
        'sha256sum "$POLICY"',
        "sha256sum",
    ):
        assert required in source
    for configuration in EXPECTED_CONFIGURATIONS:
        assert f"run_one {configuration}" in source
    assert source.index("runner_failure_blocks_audit") < source.index(
        '"$ISAACLAB_PY" -p "$AUDITOR"'
    )
    assert source.index('"$CONDA_PYTHON" "$POLICY_VALIDATOR"') < source.index(
        'cp "$POLICY"'
    )
    assert source.index('cp "$POLICY"') < source.index("run_one base")
    assert "source/results/koopman_phase8_pilot" in source
    assert "/root/EASYkoopman-phase8-pilot-v2" in source


def test_server_run_uses_one_configuration_process_for_two_policy_episodes():
    source = SERVER_RUN.read_text(encoding="utf-8")
    assert '--configuration "$configuration"' in source
    assert '--policy "$POLICY"' in source
    assert "--seed" not in source
    assert "--steps" not in source
    assert "--episode-id" not in source
    assert "2 episodes" in source or "two policy episodes" in source


def test_pullback_orders_status_scp_hash_source_runtime_validator_before_atomic_promotion():
    source = PULLBACK.read_text(encoding="utf-8")
    for required in (
        "phase8-pilot-pullback-",
        "scp_failed",
        "native_status",
        "tee_status",
        "semantic_status",
        "sha256_mismatch",
        "source_commit_mismatch",
        "runtime_version_mismatch",
        "worktree_dirty",
        "--untracked-files=all",
        "validate_phase8_pilot_policy.py",
        "pilot_policy_validator_failed",
        "validate_phase8_evidence.py",
        "server_isaac_identification_pilot",
        "validator_failed",
        "canonical_evidence_already_exists",
        "Move-Item",
        "source/results/koopman_phase8_pilot",
    ):
        assert required in source
    assert source.index("scp") < source.index("sha256_mismatch")
    assert source.index("sha256_mismatch") < source.index("source_commit_mismatch")
    assert source.index("source_commit_mismatch") < source.index(
        "validate_phase8_pilot_policy.py"
    )
    assert source.index("validate_phase8_pilot_policy.py") < source.index(
        "validate_phase8_evidence.py"
    )
    assert source.index("validate_phase8_evidence.py") < source.index("Move-Item")


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("source", "source_commit_mismatch"),
        ("runtime", "isaaclab_provenance_mismatch"),
        ("native", "native_status_invalid"),
        ("tee", "tee_status_invalid"),
        ("semantic", "semantic_status_invalid"),
        ("scp", "scp_failed:status:23"),
        ("inventory", "inventory_hash_mismatch"),
        ("hash", "sha256_mismatch"),
        ("policy", "pilot_runtime_contract_mismatch:python_entrypoint"),
        ("validator", "validator_failed"),
        ("promotion", "canonical_evidence_already_exists"),
    ],
)
def test_pullback_dynamic_mutations_fail_before_atomic_promotion(
    tmp_path: Path, mutation: str, expected_error: str
):
    repository, evidence, status, _ = _pullback_fixture(
        tmp_path, canonical_exists=mutation == "promotion"
    )
    if mutation == "source":
        (status / "source_commit.txt").write_text(f"{'b' * 40}\n", encoding="utf-8")
    elif mutation == "runtime":
        (status / "isaaclab_release_commit.txt").write_text(
            f"{'b' * 40}\n", encoding="utf-8"
        )
    elif mutation in {"native", "tee"}:
        (status / f"base.{mutation}_status").write_text("7\n", encoding="utf-8")
    elif mutation == "semantic":
        (status / "base.semantic_status").write_text("fail\n", encoding="utf-8")
    elif mutation == "inventory":
        log = next((evidence / "logs").glob("*.log"))
        log.write_text(log.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    elif mutation == "hash":
        (status / "pilot_envelope.sha256").write_text(
            f"{'0' * 64}  pilot_envelope.json\n", encoding="utf-8"
        )
    elif mutation == "policy":
        policy_path = evidence / "pilot_collection_policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["runtime_contract"]["python_entrypoint"] = "/usr/bin/python3"
        policy_path.write_bytes(_fixture_canonical_bytes(policy))
        _write_exact_inventory(evidence, status)
    elif mutation == "validator":
        log = next((evidence / "logs").glob("*.log"))
        log.write_text(log.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
        _write_exact_inventory(evidence, status)

    fake_bin = tmp_path / "fake-bin"
    _write_fake_scp(fake_bin)
    environment = dict(os.environ)
    environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
    environment["PHASE8_FAKE_EVIDENCE"] = str(evidence)
    environment["PHASE8_FAKE_STATUS"] = str(status)
    environment["PHASE8_FAKE_SCP_FAIL"] = "1" if mutation == "scp" else "0"
    result = _run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repository / "scripts" / PULLBACK.name),
            "-RepositoryRoot",
            str(repository),
            "-PythonExecutable",
            sys.executable,
        ],
        cwd=repository,
        env=environment,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert expected_error in output
    canonical = repository / "source" / "results" / "koopman_phase8_pilot"
    if mutation == "promotion":
        assert (canonical / "sentinel.txt").read_text(encoding="utf-8") == "keep\n"
    else:
        assert not canonical.exists()


def test_pullback_dynamic_happy_path_validates_then_promotes_once(tmp_path: Path):
    repository, evidence, status, source_commit = _pullback_fixture(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    _write_fake_scp(fake_bin)
    environment = dict(os.environ)
    environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
    environment["PHASE8_FAKE_EVIDENCE"] = str(evidence)
    environment["PHASE8_FAKE_STATUS"] = str(status)
    environment["PHASE8_FAKE_SCP_FAIL"] = "0"
    result = _run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repository / "scripts" / PULLBACK.name),
            "-RepositoryRoot",
            str(repository),
            "-PythonExecutable",
            sys.executable,
        ],
        cwd=repository,
        env=environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "validation_gate=phase8_external_evidence_valid" in result.stdout
    assert "qualification_level=server_isaac_identification_pilot" in result.stdout
    assert f"source_commit={source_commit}" in result.stdout
    canonical = repository / "source" / "results" / "koopman_phase8_pilot"
    assert (canonical / "pilot_envelope.json").is_file()
    assert not (canonical / "all_files.sha256").exists()


def test_runbook_has_exact_operator_sequence_agent_responsibility_and_claim_boundary():
    text = RUNBOOK.read_text(encoding="utf-8")
    for heading in (
        "## Evidence Vocabulary",
        "## Pilot Policy",
        "## Local Pilot Preflight",
        "## Offline Bundle",
        "## Server Exact-Eight Pilot",
        "## Pilot Health Audit",
        "## Pullback",
        "## Failure Handling",
        "## Main Protocol Checkpoint",
        "## Claim Boundary",
    ):
        assert heading in text
    for required in (
        "8 configurations",
        "2 episodes",
        "128 transitions",
        "/root/EASYkoopman-phase8-pilot-v2",
        "agent performs",
        "collection health",
        "does not prove identification",
        "does not prove OOD",
        "does not prove MPC",
    ):
        assert required in text
