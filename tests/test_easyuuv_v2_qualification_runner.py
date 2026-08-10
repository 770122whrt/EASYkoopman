"""Isaac-free contracts for the Phase 6 qualification runner and merger."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest

import workflows.qualify_easyuuv_v2 as qualification_runner

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS, qualification_record
from workflows.easyuuv_v2_qualification_artifact import (
    EXPECTED_ISAAC_LAB_VERSION,
    EXPECTED_ISAAC_SIM_VERSION,
    EXPECTED_TASK_ID,
    QUALIFICATION_SCHEMA_VERSION,
    SERVER_EVIDENCE_LEVEL,
    validate_qualification_payload,
)
from workflows.merge_easyuuv_v2_qualification import merge_qualification_results
from workflows.qualify_easyuuv_v2 import (
    DEFAULT_RESULT_ROOT,
    _atomic_write_json,
    _empty_row,
    _merge_step_summary,
    _record_failure,
    build_runtime_provenance,
    build_argument_parser,
    deterministic_excitation,
    normalize_isaac_sim_version,
    resolve_output_path,
    summarize_actual_telemetry,
)


@pytest.fixture
def local_tmp_path() -> Path:
    """Keep scratch files under the repository on restricted Windows runners."""
    scratch_root = Path(__file__).resolve().parents[1] / ".pytest-tmp"
    scratch_root.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="qualification-runner-", dir=scratch_root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _row(configuration: str) -> dict:
    topology = qualification_record(configuration)
    steps = 64 if configuration == "base" else 8
    return {
        "configuration": configuration,
        "thruster_count": topology["thruster_count"],
        "control_channels": list(topology["control_channels"]),
        "control_mask": list(topology["control_mask"]),
        "declared_control_rank": topology["declared_control_rank"],
        "environment_created": True,
        "reset_passed": True,
        "steps_completed": steps,
        "action_min": -0.1,
        "action_max": 0.1,
        "motor_min": -0.25,
        "motor_max": 0.25,
        "motor_vector_length": topology["thruster_count"],
        "nonfinite_count": 0,
        "dimension_mismatch_count": 0,
        "seed": 0,
        "status": "pass",
        "reason_codes": [],
    }


def _single_row_payload(
    configuration: str,
    *,
    actual_isaac_sim: str = EXPECTED_ISAAC_SIM_VERSION,
    actual_isaac_lab: str = EXPECTED_ISAAC_LAB_VERSION,
    source_commit: str = "a" * 40,
) -> dict:
    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "evidence_level": SERVER_EVIDENCE_LEVEL,
        "expected_isaac_sim": EXPECTED_ISAAC_SIM_VERSION,
        "expected_isaac_lab": EXPECTED_ISAAC_LAB_VERSION,
        "actual_isaac_sim": actual_isaac_sim,
        "actual_isaac_lab": actual_isaac_lab,
        "runtime_provenance": {
            "isaac_sim_distribution": "5.0.0.0",
            "isaac_lab_distribution": "0.45.9",
            "isaac_lab_repo_commit": "c" * 40,
            "isaac_lab_repo_tag": "v2.2.1",
        },
        "task_id": EXPECTED_TASK_ID,
        "source_commit": source_commit,
        "results": [_row(configuration)],
    }


def _write_row(path: Path, configuration: str, **overrides: object) -> Path:
    payload = _single_row_payload(configuration)
    payload.update(overrides)
    path.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_all_rows(directory: Path) -> list[Path]:
    return [
        _write_row(directory / f"{configuration}.json", configuration)
        for configuration in SUPPORTED_EMBODIMENTS
    ]


def test_runner_help_contract_is_available_without_isaac_imports():
    parser = build_argument_parser()
    help_text = parser.format_help()

    for option in (
        "--task",
        "--configuration",
        "--steps",
        "--seed",
        "--num-envs",
        "--headless",
        "--output-json",
        "--result-root",
    ):
        assert option in help_text
    assert tuple(parser._option_string_actions["--configuration"].choices) == SUPPORTED_EMBODIMENTS


def test_importing_qualification_runner_is_stdlib_only():
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(project_root), existing_pythonpath) if part
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import workflows.qualify_easyuuv_v2; "
                "blocked = sorted(name for name in sys.modules if "
                "name == 'torch' or name.startswith('torch.') or "
                "name == 'gymnasium' or name.startswith('gymnasium.') or "
                "name == 'omni' or name.startswith('omni.') or "
                "name == 'easyuuv_nc.env' or name.startswith('easyuuv_nc.env.')); "
                "assert not blocked, blocked"
            ),
        ],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert probe.returncode == 0, probe.stderr


def test_all_app_started_gym_consumers_register_explicitly_after_launcher():
    project_root = Path(__file__).resolve().parents[1]
    consumers = (
        "scripts/phase6_probe_gym_tasks.py",
        "workflows/qualify_easyuuv_v2.py",
        "workflows/gen_policy.py",
        "workflows/play_controller.py",
        "workflows/play_eval.py",
        "workflows/play_eval_step.py",
        "workflows/play_eval_task2.py",
        "workflows/play_ppo_koopman.py",
        "workflows/train.py",
        "workflows/train_ppo_koopman.py",
        "easyuuv_nc/probe/probe_clean_package.py",
        "easyuuv_nc/probe/probe_subfolder_bootstrap.py",
        "easyuuv_nc/workflows/train.py",
        "easyuuv_nc/workflows/adapt.py",
    )

    for relative_path in consumers:
        source = (project_root / relative_path).read_text(encoding="utf-8")
        assert "register_gym_tasks()" in source, relative_path
        assert source.index("simulation_app = app_launcher.app") < source.index(
            "register_gym_tasks()"
        ), relative_path


@pytest.mark.parametrize(("option", "value"), (("--steps", "0"), ("--num-envs", "-1")))
def test_runner_rejects_nonpositive_execution_counts(option: str, value: str):
    arguments = [
        "--configuration",
        "base",
        "--steps",
        "8",
        "--output-json",
        "base.json",
        option,
        value,
    ]

    with pytest.raises(SystemExit):
        build_argument_parser().parse_args(arguments)


def test_deterministic_excitation_cycles_signed_channels_and_is_bounded():
    values = [deterministic_excitation(step, (1, 1, 1, 1)) for step in range(8)]

    assert values == [
        (0.1, 0.0, 0.0, 0.0),
        (-0.1, 0.0, 0.0, 0.0),
        (0.0, 0.1, 0.0, 0.0),
        (0.0, -0.1, 0.0, 0.0),
        (0.0, 0.0, 0.1, 0.0),
        (0.0, 0.0, -0.1, 0.0),
        (0.0, 0.0, 0.0, 0.1),
        (0.0, 0.0, 0.0, -0.1),
    ]
    assert max(abs(value) for action in values for value in action) <= 0.1


@pytest.mark.parametrize("configuration", ("uuv4", "uuv4_angled"))
def test_underactuated_excitation_never_sets_yaw(configuration: str):
    mask = qualification_record(configuration)["control_mask"]

    values = [deterministic_excitation(step, mask) for step in range(24)]

    assert all(action[2] == 0.0 for action in values)


def test_default_output_root_is_canonical_without_creating_evidence():
    project_root = Path(__file__).resolve().parents[1]

    assert DEFAULT_RESULT_ROOT == (
        project_root / "source" / "results" / "koopman_phase6"
    )


def test_output_path_rejects_escape_from_explicit_result_root(local_tmp_path: Path):
    result_root = local_tmp_path / "allowed"

    with pytest.raises(ValueError, match="output_outside_result_root"):
        resolve_output_path(local_tmp_path / "outside.json", result_root)


def test_output_path_creates_confined_parent(local_tmp_path: Path):
    result_root = local_tmp_path / "allowed"
    output = result_root / "rows" / "base.json"

    resolved = resolve_output_path(output, result_root)

    assert resolved.parent.is_dir()
    assert resolved.is_relative_to(result_root.resolve())


def test_output_path_rejects_symlinked_parent_component(
    local_tmp_path: Path, monkeypatch
):
    result_root = local_tmp_path / "allowed"
    output = result_root / "rows" / "base.json"
    output.parent.mkdir(parents=True)
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == output.parent or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="output_symlink_component"):
        resolve_output_path(output, result_root)


def test_atomic_writer_revalidates_confinement_immediately_before_write(
    local_tmp_path: Path, monkeypatch
):
    result_root = local_tmp_path / "allowed"
    output = resolve_output_path(result_root / "rows" / "base.json", result_root)
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == output.parent or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="output_symlink_component"):
        _atomic_write_json(output, {"status": "fail"}, result_root=result_root)


def test_actual_telemetry_is_required():
    with pytest.raises(RuntimeError, match="missing_actual_telemetry"):
        summarize_actual_telemetry(
            pid_value=None,
            motor_values=None,
            expected_motor_length=8,
        )


def test_actual_telemetry_summary_uses_real_values_and_counts_shape_mismatch():
    summary = summarize_actual_telemetry(
        pid_value=[[0.05, -0.1, 0.0, 0.1]],
        motor_values=[[0.25, -0.2, 0.0, 0.1, -0.1, 0.2]],
        expected_motor_length=8,
    )

    assert summary == {
        "action_min": -0.1,
        "action_max": 0.1,
        "motor_min": -0.2,
        "motor_max": 0.25,
        "motor_vector_length": 6,
        "nonfinite_count": 0,
        "dimension_mismatch_count": 1,
    }


def test_actual_telemetry_summary_counts_nonfinite_values():
    summary = summarize_actual_telemetry(
        pid_value=[[0.0, float("nan"), 0.0, 0.0]],
        motor_values=[[0.0] * 7 + [float("inf")]],
        expected_motor_length=8,
    )

    assert summary["nonfinite_count"] == 2


def test_nonfinite_telemetry_failure_row_is_strict_json_and_reloadable(
    local_tmp_path: Path,
):
    summary = summarize_actual_telemetry(
        pid_value=[[float("nan"), float("inf"), float("-inf"), float("nan")]],
        motor_values=[[float("inf")] * 8],
        expected_motor_length=8,
    )
    row = _empty_row("base", seed=0)
    _merge_step_summary(row, summary, first_step=True)
    _record_failure(row, "nonfinite_actual_telemetry")
    payload = _single_row_payload("base")
    payload["results"] = [row]
    output = local_tmp_path / "base-failed.json"

    _atomic_write_json(output, payload)
    reloaded = json.loads(output.read_text(encoding="utf-8"))

    assert reloaded["results"][0]["status"] == "fail"
    assert reloaded["results"][0]["reason_codes"] == [
        "nonfinite_actual_telemetry"
    ]
    assert reloaded["results"][0]["nonfinite_count"] == 12
    for field in ("action_min", "action_max", "motor_min", "motor_max"):
        assert reloaded["results"][0][field] == 0.0


def test_environment_close_failure_still_closes_simulator_and_marks_payload():
    close_runtime = getattr(qualification_runner, "_close_runtime", None)
    record_cleanup = getattr(
        qualification_runner, "_record_cleanup_failures", None
    )
    assert callable(close_runtime)
    assert callable(record_cleanup)
    events: list[str] = []

    class FailingEnvironment:
        def close(self) -> None:
            events.append("environment")
            raise RuntimeError("environment close exploded")

    class SimulationApp:
        def close(self) -> None:
            events.append("simulation_app")

    payload = _single_row_payload("base")

    failures = close_runtime(FailingEnvironment(), SimulationApp())
    exit_code = record_cleanup(payload, failures, exit_code=0)

    assert events == ["environment", "simulation_app"]
    assert failures == ["environment_close_failed"]
    assert exit_code == 1
    assert payload["results"][0]["status"] == "fail"
    assert payload["results"][0]["reason_codes"] == [
        "environment_close_failed"
    ]


def test_preflight_failure_writes_distinct_machine_readable_evidence(
    local_tmp_path: Path, monkeypatch, capsys
):
    result_root = local_tmp_path / "results"
    output = result_root / "rows" / "base.json"

    def fail_preflight(args):
        raise RuntimeError("runtime_version_provenance_unavailable")

    monkeypatch.setattr(
        qualification_runner, "run_isaac_qualification", fail_preflight
    )

    exit_code = qualification_runner.main(
        [
            "--configuration",
            "base",
            "--steps",
            "64",
            "--output-json",
            str(output),
            "--result-root",
            str(result_root),
        ]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert payload["artifact_kind"] == "preflight_failure"
    assert payload["eligible_for_merge"] is False
    assert payload["evidence_level"] == "server_preflight_failure"
    assert payload["results"][0]["configuration"] == "base"
    assert payload["results"][0]["status"] == "fail"
    assert payload["results"][0]["reason_codes"] == [
        "runtime_version_provenance_unavailable"
    ]
    assert "ERROR: runtime_version_provenance_unavailable" in capsys.readouterr().err


def test_runtime_provenance_uses_installed_sim_and_exact_isaaclab_release_tag():
    provenance = build_runtime_provenance(
        isaac_sim_distribution="5.0.0.0",
        isaac_lab_distribution="0.45.9",
        isaac_lab_repo_commit="c" * 40,
        isaac_lab_repo_tag="v2.2.1",
    )

    assert provenance == {
        "actual_isaac_sim": "5.0",
        "actual_isaac_lab": "2.2.1",
        "runtime_provenance": {
            "isaac_sim_distribution": "5.0.0.0",
            "isaac_lab_distribution": "0.45.9",
            "isaac_lab_repo_commit": "c" * 40,
            "isaac_lab_repo_tag": "v2.2.1",
        },
    }


def test_source_commit_rejects_tracked_worktree_changes(monkeypatch):
    def fake_git_output(repository: Path, *arguments: str) -> str:
        if arguments == ("status", "--porcelain=v1", "--untracked-files=no"):
            return " M workflows/qualify_easyuuv_v2.py"
        if arguments == ("rev-parse", "HEAD"):
            return "a" * 40
        raise AssertionError(arguments)

    monkeypatch.setattr(qualification_runner, "_git_output", fake_git_output)

    with pytest.raises(RuntimeError, match="source_worktree_tracked_dirty"):
        qualification_runner._repository_commit()


def test_source_commit_accepts_clean_tracked_tree(monkeypatch):
    def fake_git_output(repository: Path, *arguments: str) -> str:
        if arguments == ("status", "--porcelain=v1", "--untracked-files=no"):
            return ""
        if arguments == ("rev-parse", "HEAD"):
            return "a" * 40
        raise AssertionError(arguments)

    monkeypatch.setattr(qualification_runner, "_git_output", fake_git_output)

    assert qualification_runner._repository_commit() == "a" * 40


def test_bundle_preparation_script_binds_tested_head_to_bundle_and_sidecar():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "phase6_prepare_bundle.ps1"
    ).read_text(encoding="utf-8")

    assert "status --porcelain=v1" in script
    assert "--untracked-files=no" not in script
    assert "rev-parse" in script
    assert '"$Branch^{commit}"' in script
    assert "bundle" in script
    assert "list-heads" in script
    assert "expected-source-commit.txt" in script
    assert "bundle_ref_mismatch" in script


def test_bundle_preparation_rejects_untracked_source_before_transfer(
    local_tmp_path: Path,
):
    project_root = Path(__file__).resolve().parents[1]
    repository = local_tmp_path / "prepare-untracked-repo"
    _init_pullback_test_repository(repository)
    (repository / ".gitignore").write_text(".pytest-tmp/\n", encoding="utf-8")
    scripts = repository / "scripts"
    scripts.mkdir()
    (scripts / "phase6_server_bootstrap.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n"
    )
    subprocess.run(
        ["git", "add", ".gitignore", "scripts/phase6_server_bootstrap.sh"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Phase6 Test",
            "-c",
            "user.email=phase6@example.invalid",
            "commit",
            "-m",
            "bundle inputs",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    (repository / "local-config.yaml").write_text("unsafe: true\n", encoding="utf-8")
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell unavailable")

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "scripts" / "phase6_prepare_bundle.ps1"),
            "-RepositoryRoot",
            str(repository),
            "-Branch",
            "v2.0-multi-configuration",
            "-TransferDirectory",
            ".pytest-tmp/phase6-transfer",
            "-CanonicalEvidenceDirectory",
            "canonical-evidence",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "worktree_dirty" in completed.stdout + completed.stderr
    assert not (repository / ".pytest-tmp" / "phase6-transfer").exists()


def test_bundle_preparation_rejects_preexisting_canonical_evidence():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "phase6_prepare_bundle.ps1"
    ).read_text(encoding="utf-8")

    assert "CanonicalEvidenceDirectory" in script
    assert "canonical_evidence_already_exists" in script
    assert script.index("canonical_evidence_already_exists") < script.index(
        "bundle create"
    )


def test_server_evidence_chain_has_no_tracked_bytecode_and_disables_writes():
    project_root = Path(__file__).resolve().parents[1]
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    tracked_bytecode = [
        path
        for path in tracked
        if "/__pycache__/" in f"/{path}" and path.endswith(".pyc")
    ]
    server_script = (
        project_root / "scripts" / "phase6_server_qualification.sh"
    ).read_text(encoding="utf-8")
    install_helper = (
        project_root / "scripts" / "phase6_offline_install.sh"
    ).read_text(encoding="utf-8")

    assert tracked_bytecode == []
    assert "export PYTHONDONTWRITEBYTECODE=1" in server_script
    assert server_script.index("export PYTHONDONTWRITEBYTECODE=1") < (
        server_script.index('source "$OFFLINE_INSTALL_HELPER"')
    )
    assert '"$isaaclab_python" -p -m pip install' in install_helper
    assert "--no-deps --no-build-isolation --no-index" in install_helper


def test_all_server_runner_commands_use_isaaclab_launcher_and_absolute_paths():
    project_root = Path(__file__).resolve().parents[1]
    runbook = (project_root / "docs" / "phase6_easyuuv_v2_qualification_runbook.md").read_text(
        encoding="utf-8"
    )
    server_script = (
        project_root / "scripts" / "phase6_server_qualification.sh"
    ).read_text(encoding="utf-8")
    launcher_command = (
        "/root/IsaacLab/isaaclab.sh -p -u "
        "/root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py"
    )

    assert runbook.count(launcher_command) == 8
    assert "python -u workflows/qualify_easyuuv_v2.py" not in runbook
    assert 'ISAACLAB_PY="/root/IsaacLab/isaaclab.sh"' in server_script
    assert '"$ISAACLAB_PY" -p -u "$RUNNER"' in server_script
    assert '--result-root "$RESULT_ROOT"' in server_script


def test_local_full_suite_uses_ignored_phase6_basetemp():
    project_root = Path(__file__).resolve().parents[1]
    runbook = (
        project_root / "docs" / "phase6_easyuuv_v2_qualification_runbook.md"
    ).read_text(encoding="utf-8")
    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")

    assert ".pytest-tmp/" in gitignore
    assert "--basetemp .pytest-tmp/phase6-full-suite" in runbook
    assert "--basetemp .pytest-phase6" not in runbook


def test_server_probe_starts_app_before_resolving_all_four_gym_task_ids():
    project_root = Path(__file__).resolve().parents[1]
    probe = (project_root / "scripts" / "phase6_probe_gym_tasks.py").read_text(
        encoding="utf-8"
    )
    server_script = (
        project_root / "scripts" / "phase6_server_qualification.sh"
    ).read_text(encoding="utf-8")
    expected_ids = (
        "EasyUUV-Direct-v1",
        "EasyUUV-Direct-Parametric-v1",
        "EasyUUV-Direct-Parametric-SatObs-v1",
        "EasyUUV-Direct-Parametric-Wide256-v1",
    )

    assert probe.index("simulation_app = app_launcher.app") < probe.index(
        "import gymnasium as gym"
    )
    assert probe.index("simulation_app = app_launcher.app") < probe.index(
        "from easyuuv_nc import register_gym_tasks"
    )
    assert probe.index("simulation_app = app_launcher.app") < probe.index(
        "register_gym_tasks()"
    )
    assert probe.index("sys.path.insert") < probe.index(
        "from isaaclab_app import AppLauncher"
    )
    assert "gym.spec(task_id)" in probe
    assert all(task_id in probe for task_id in expected_ids)
    assert "EMBODIMENT_USD_PATH.is_file()" in probe
    assert '"$ISAACLAB_PY" -p "$TASK_PROBE"' in server_script


def test_server_bootstrap_and_execution_are_fail_closed_before_merge():
    project_root = Path(__file__).resolve().parents[1]
    bootstrap = (
        project_root / "scripts" / "phase6_server_bootstrap.sh"
    ).read_text(encoding="utf-8")
    qualification = (
        project_root / "scripts" / "phase6_server_qualification.sh"
    ).read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in bootstrap
    assert "target_directory_already_exists" in bootstrap
    assert "^[0-9a-f]{40}$" in bootstrap
    assert "bundle list-heads" in bootstrap
    assert "bundle_ref_mismatch" in bootstrap
    assert "server_head_mismatch" in bootstrap
    assert "status --porcelain" in bootstrap
    assert "server_clone_not_clean" in bootstrap
    assert 'exec bash "$TARGET_ROOT/scripts/phase6_server_qualification.sh"' in bootstrap

    assert "set -Eeuo pipefail" in qualification
    assert "tracked_source_drift" in qualification
    assert qualification.index("tracked_source_drift") < qualification.index(
        "mkdir -p"
    )
    assert 'pipeline_status=("${PIPESTATUS[@]}")' in qualification
    assert "runner_failure_blocks_merge" in qualification
    assert qualification.index("runner_failure_blocks_merge") < qualification.index(
        '"$ISAACLAB_PY" -p "$MERGER"'
    )
    assert '"$ISAACLAB_PY" -p "$VALIDATOR"' in qualification
    assert "sha256sum" in qualification


def test_server_version_preflight_persists_expected_actual_and_command_status(
    local_tmp_path: Path,
):
    project_root = Path(__file__).resolve().parents[1]
    helper = project_root / "scripts" / "phase6_server_preflight.sh"
    qualification = (
        project_root / "scripts" / "phase6_server_qualification.sh"
    ).read_text(encoding="utf-8")
    result_root = local_tmp_path / "preflight-evidence"
    if sys.platform == "win32":
        git_executable = Path(shutil.which("git") or "")
        bash = git_executable.parent.parent / "bin" / "bash.exe"
    else:
        bash = Path(shutil.which("bash") or "")
    if not bash.is_file():
        pytest.skip("bash executable unavailable")

    assert helper.is_file()
    completed = subprocess.run(
        [
            str(bash),
            "-c",
            (
                f"source '{helper.as_posix()}'; "
                f"phase6_require_preflight_value '{result_root.as_posix()}' "
                "isaaclab_repo_tag v2.2.1 v2.3.0 0"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    failure = (result_root / "preflight_failure.txt").read_text(encoding="utf-8")
    assert "check=isaaclab_repo_tag" in failure
    assert "expected=v2.2.1" in failure
    assert "actual=v2.3.0" in failure
    assert "command_status=0" in failure
    assert "expected=v2.2.1;actual=v2.3.0;command_status=0" in completed.stderr
    assert qualification.index('mkdir -p "$PREFLIGHT_ROOT" "$RESULT_ROOT/logs"') < (
        qualification.index("isaaclab_tag_status")
    )
    assert "phase6_require_preflight_value" in qualification


def test_server_editable_install_is_offline_and_persists_command_failure(
    local_tmp_path: Path,
):
    project_root = Path(__file__).resolve().parents[1]
    preflight_helper = project_root / "scripts" / "phase6_server_preflight.sh"
    install_helper = project_root / "scripts" / "phase6_offline_install.sh"
    qualification = (
        project_root / "scripts" / "phase6_server_qualification.sh"
    ).read_text(encoding="utf-8")
    result_root = local_tmp_path / "offline-install-evidence"
    fake_launcher = local_tmp_path / "fake-isaaclab.sh"
    calls = local_tmp_path / "fake-launcher-calls.txt"
    fake_launcher.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$PHASE6_FAKE_CALLS\"\n"
        "if [[ \"$*\" == *'importlib.metadata'* ]]; then\n"
        "  printf '%s\\n' 'PHASE6_ACTUAL_SETUPTOOLS=75.8.0'\n"
        "  exit 0\n"
        "fi\n"
        "exit 7\n",
        encoding="utf-8",
        newline="\n",
    )
    fake_launcher.chmod(0o755)
    if sys.platform == "win32":
        git_executable = Path(shutil.which("git") or "")
        bash = git_executable.parent.parent / "bin" / "bash.exe"
    else:
        bash = Path(shutil.which("bash") or "")
    if not bash.is_file():
        pytest.skip("bash executable unavailable")

    assert install_helper.is_file()
    environment = os.environ.copy()
    environment["PHASE6_FAKE_CALLS"] = str(calls)
    completed = subprocess.run(
        [
            str(bash),
            "-c",
            (
                f"source '{preflight_helper.as_posix()}'; "
                f"source '{install_helper.as_posix()}'; "
                f"phase6_prepare_offline_python_env '{result_root.as_posix()}' "
                f"'{fake_launcher.as_posix()}' '{project_root.as_posix()}'"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 1
    assert (result_root / "setuptools_version.txt").read_text().strip() == "75.8.0"
    failure = (result_root / "preflight_failure.txt").read_text(encoding="utf-8")
    assert "check=editable_install" in failure
    assert "expected=0" in failure
    assert "actual=7" in failure
    assert "command_status=7" in failure
    install_call = calls.read_text(encoding="utf-8").splitlines()[-1]
    assert "-p -m pip install -e" in install_call
    assert "--no-deps --no-build-isolation --no-index" in install_call
    assert 'source "$OFFLINE_INSTALL_HELPER"' in qualification
    assert "phase6_prepare_offline_python_env" in qualification


def test_server_pipeline_gate_blocks_successful_runner_when_log_capture_fails(
    local_tmp_path: Path,
):
    project_root = Path(__file__).resolve().parents[1]
    helper = project_root / "scripts" / "phase6_pipeline_gate.sh"
    server_script = (
        project_root / "scripts" / "phase6_server_qualification.sh"
    ).read_text(encoding="utf-8")
    result_root = local_tmp_path / "pipeline-evidence"
    (result_root / "exit_codes").mkdir(parents=True)
    (result_root / "log_exit_codes").mkdir()
    if sys.platform == "win32":
        git_executable = Path(shutil.which("git") or "")
        bash = git_executable.parent.parent / "bin" / "bash.exe"
    else:
        bash = Path(shutil.which("bash") or "")
    if not bash.is_file():
        pytest.skip("bash executable unavailable")

    completed = subprocess.run(
        [
            str(bash),
            "-c",
            (
                f"source '{helper.as_posix()}'; "
                f"phase6_record_pipeline_status '{result_root.as_posix()}' base 0 1"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert (result_root / "exit_codes" / "base.txt").read_text().strip() == "0"
    assert (result_root / "log_exit_codes" / "base.txt").read_text().strip() == "1"
    assert "log_capture_failed:base:1" in completed.stderr
    assert 'pipeline_status=("${PIPESTATUS[@]}")' in server_script
    assert "phase6_record_pipeline_status" in server_script


def test_pullback_stages_then_checks_native_exits_hash_and_commits_before_promotion():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "phase6_pullback.ps1"
    ).read_text(encoding="utf-8")

    assert "[Guid]::NewGuid()" in script
    assert "staging_directory_already_exists" in script
    assert "scp_failed" in script
    assert "$LASTEXITCODE" in script
    assert "^[0-9a-f]{64}" in script
    assert "sha256_mismatch" in script
    assert "source_commit_mismatch" in script
    assert "--expected-source-commit-file" in script
    assert "--expected-isaaclab-commit-file" in script
    assert "--expected-isaaclab-tag-file" in script
    assert "validator_failed" in script
    assert "status --porcelain=v1" in script
    assert "--untracked-files=no" not in script
    assert script.index("sha256_mismatch") < script.index("Move-Item")
    assert script.index("validator_failed") < script.index("Move-Item")


def _init_pullback_test_repository(path: Path) -> str:
    path.mkdir()
    subprocess.run(["git", "init", "-b", "v2.0-multi-configuration"], cwd=path, check=True)
    (path / "tracked.txt").write_text("tested\n", encoding="utf-8")
    (path / ".gitignore").write_text(".transfer/\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt", ".gitignore"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Phase6 Test",
            "-c",
            "user.email=phase6@example.invalid",
            "commit",
            "-m",
            "tested source",
        ],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _run_pullback_preflight(
    project_root: Path, repository: Path, expected_commit: str, marker: Path
) -> subprocess.CompletedProcess[str]:
    transfer = repository / ".transfer"
    transfer.mkdir()
    (transfer / "expected-source-commit.txt").write_text(
        expected_commit + "\n", encoding="utf-8"
    )
    fake_bin = repository / "fake-bin"
    fake_bin.mkdir()
    environment = os.environ.copy()
    environment["PHASE6_FAKE_SCP_MARKER"] = str(marker)
    environment["PATH"] = os.pathsep.join((str(fake_bin), environment["PATH"]))
    if sys.platform == "win32":
        (fake_bin / "scp.cmd").write_text(
            "@echo off\r\necho called>\"%PHASE6_FAKE_SCP_MARKER%\"\r\nexit /b 99\r\n",
            encoding="utf-8",
        )
    else:
        fake_scp = fake_bin / "scp"
        fake_scp.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' called > \"$PHASE6_FAKE_SCP_MARKER\"\nexit 99\n",
            encoding="utf-8",
            newline="\n",
        )
        fake_scp.chmod(0o755)
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell unavailable")
    return subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "scripts" / "phase6_pullback.ps1"),
            "-RepositoryRoot",
            str(repository),
            "-TransferDirectory",
            ".transfer",
            "-CanonicalEvidenceDirectory",
            "canonical-evidence",
            "-Remote",
            "must-not-be-contacted",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_pullback_rejects_local_head_sidecar_mismatch_before_scp(local_tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    repository = local_tmp_path / "head-mismatch-repo"
    _init_pullback_test_repository(repository)
    marker = local_tmp_path / "scp-head-mismatch-called.txt"

    completed = _run_pullback_preflight(project_root, repository, "0" * 40, marker)

    assert completed.returncode != 0
    assert "local_head_mismatch" in completed.stdout + completed.stderr
    assert not marker.exists()


def test_pullback_rejects_tracked_drift_before_scp(local_tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    repository = local_tmp_path / "tracked-drift-repo"
    head = _init_pullback_test_repository(repository)
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
    marker = local_tmp_path / "scp-tracked-drift-called.txt"

    completed = _run_pullback_preflight(project_root, repository, head, marker)

    assert completed.returncode != 0
    assert "worktree_dirty" in completed.stdout + completed.stderr
    assert not marker.exists()


def test_pullback_rejects_untracked_source_before_scp(local_tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    repository = local_tmp_path / "untracked-source-repo"
    head = _init_pullback_test_repository(repository)
    (repository / "local-config.yaml").write_text("unsafe: true\n", encoding="utf-8")
    marker = local_tmp_path / "scp-untracked-source-called.txt"

    completed = _run_pullback_preflight(project_root, repository, head, marker)

    assert completed.returncode != 0
    assert "worktree_dirty" in completed.stdout + completed.stderr
    assert not marker.exists()


@pytest.mark.parametrize("raw", ("5.0", "5.0.0.0", "5.0.0.0+linux-x86_64"))
def test_isaac_sim_distribution_is_normalized_to_semantic_baseline(raw: str):
    assert normalize_isaac_sim_version(raw) == "5.0"


@pytest.mark.parametrize(
    "bad_tag",
    ("2.2", "release-2.2.1", "v2.2.1-dirty", "v2.3.0", ""),
)
def test_runtime_provenance_rejects_nonbaseline_or_inexact_isaaclab_tag(bad_tag: str):
    with pytest.raises(RuntimeError, match="isaac_lab_release_provenance_invalid"):
        build_runtime_provenance(
            isaac_sim_distribution="5.0.0.0",
            isaac_lab_distribution="0.45.9",
            isaac_lab_repo_commit="c" * 40,
            isaac_lab_repo_tag=bad_tag,
        )


def test_merge_valid_eight_rows_is_deterministic_and_strict(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    output = local_tmp_path / "merged" / "qualification.json"

    first = merge_qualification_results(inputs, output)
    first_bytes = output.read_bytes()
    second = merge_qualification_results(list(reversed(inputs)), output)

    assert first == second
    assert output.read_bytes() == first_bytes
    assert [row["configuration"] for row in first["results"]] == list(SUPPORTED_EMBODIMENTS)
    assert validate_qualification_payload(first)["qualification_gate"] == "server_pass"


def test_merge_rejects_missing_configuration_without_replacing_output(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)[:-1]
    output = local_tmp_path / "qualification.json"
    output.write_text("preserve-me", encoding="utf-8")

    with pytest.raises(ValueError, match="configuration_set_mismatch"):
        merge_qualification_results(inputs, output)

    assert output.read_text(encoding="utf-8") == "preserve-me"


def test_merge_rejects_duplicate_before_set_check(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    duplicate = local_tmp_path / "duplicate-base.json"
    duplicate.write_text(inputs[0].read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate_configuration"):
        merge_qualification_results([*inputs, duplicate], local_tmp_path / "qualification.json")


def test_merge_rejects_extra_configuration(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    extra_payload = deepcopy(_single_row_payload("base"))
    extra_payload["results"][0]["configuration"] = "heavy_duty"
    extra = local_tmp_path / "heavy_duty.json"
    extra.write_text(json.dumps(extra_payload), encoding="utf-8")

    with pytest.raises(ValueError, match="configuration_set_mismatch"):
        merge_qualification_results([*inputs, extra], local_tmp_path / "qualification.json")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("actual_isaac_sim", "5.1", "actual_version_disagreement"),
        ("actual_isaac_lab", "2.3.0", "actual_version_disagreement"),
        ("task_id", "OtherTask-v0", "metadata_disagreement"),
        ("source_commit", "b" * 40, "metadata_disagreement"),
    ),
)
def test_merge_rejects_metadata_disagreement(
    local_tmp_path: Path, field: str, value: str, reason: str
):
    inputs = _write_all_rows(local_tmp_path)
    changed = json.loads(inputs[-1].read_text(encoding="utf-8"))
    changed[field] = value
    inputs[-1].write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(ValueError, match=reason):
        merge_qualification_results(inputs, local_tmp_path / "qualification.json")


def test_merge_rejects_more_than_one_result_per_input(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    payload = json.loads(inputs[0].read_text(encoding="utf-8"))
    payload["results"].append(deepcopy(payload["results"][0]))
    inputs[0].write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="single_result_required"):
        merge_qualification_results(inputs, local_tmp_path / "qualification.json")


def test_merge_requires_runtime_provenance_even_when_all_rows_omit_it(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    for path in inputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        del payload["runtime_provenance"]
        path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata_missing:runtime_provenance"):
        merge_qualification_results(inputs, local_tmp_path / "qualification.json")


def test_merge_rejects_consistently_forged_runtime_release_tag(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    for path in inputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["runtime_provenance"]["isaac_lab_repo_tag"] = "v2.3.0"
        path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="runtime_provenance_invalid"):
        merge_qualification_results(inputs, local_tmp_path / "qualification.json")
