"""Run one real Isaac smoke and write one EasyUUV v2 qualification row.

The module-level helpers are deliberately Isaac-free.  Isaac and Gym are imported
only after :class:`AppLauncher` starts inside :func:`run_isaac_qualification`.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS, qualification_record
from workflows.easyuuv_v2_qualification_artifact import (
    EXPECTED_ISAAC_LAB_DIRTY_FILES,
    EXPECTED_ISAAC_LAB_DISTRIBUTION,
    EXPECTED_ISAAC_LAB_PATCH_SHA256,
    EXPECTED_ISAAC_LAB_RELEASE_COMMIT,
    EXPECTED_ISAAC_LAB_RELEASE_TAG,
    EXPECTED_ISAAC_LAB_REPO_COMMIT,
    EXPECTED_ISAAC_LAB_VERSION,
    EXPECTED_ISAAC_SIM_VERSION,
    QUALIFICATION_SCHEMA_VERSION,
    SERVER_EVIDENCE_LEVEL,
)


DEFAULT_RESULT_ROOT = PROJECT_ROOT / "source" / "results" / "koopman_phase6"
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_LAB_RELEASE_TAG_RE = re.compile(r"^v?(\d+\.\d+\.\d+)$")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the Isaac-free public CLI parser."""
    parser = argparse.ArgumentParser(
        description="Run one EasyUUV v2 configuration qualification smoke."
    )
    parser.add_argument("--task", default="EasyUUV-Direct-v1")
    parser.add_argument(
        "--configuration", required=True, choices=SUPPORTED_EMBODIMENTS
    )
    parser.add_argument("--steps", required=True, type=_positive_int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-envs", type=_positive_int, default=1)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument(
        "--result-root",
        type=Path,
        default=DEFAULT_RESULT_ROOT,
        help="Explicit root that must contain --output-json.",
    )
    return parser


def deterministic_excitation(
    step: int, control_mask: Iterable[int]
) -> tuple[float, float, float, float]:
    """Cycle ``+0.1/-0.1`` across roll, pitch, yaw and depth."""
    mask = tuple(int(value) for value in control_mask)
    if len(mask) != 4 or any(value not in (0, 1) for value in mask):
        raise ValueError("control_mask_invalid")
    channel = (int(step) // 2) % 4
    amplitude = 0.1 if int(step) % 2 == 0 else -0.1
    action = [0.0, 0.0, 0.0, 0.0]
    action[channel] = amplitude * mask[channel]
    return tuple(action)  # type: ignore[return-value]


def resolve_output_path(output_path: str | Path, result_root: str | Path) -> Path:
    """Resolve and create a result path only when it stays below ``result_root``."""
    root = Path(os.path.abspath(Path(result_root).expanduser()))
    root.mkdir(parents=True, exist_ok=True)
    output = Path(os.path.abspath(Path(output_path).expanduser()))
    _revalidate_confined_output(output, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    return _revalidate_confined_output(output, root)


def _revalidate_confined_output(
    output_path: str | Path, result_root: str | Path
) -> Path:
    """Reject escapes and existing symlink components at the write boundary."""
    lexical_root = Path(os.path.abspath(Path(result_root).expanduser()))
    lexical_output = Path(os.path.abspath(Path(output_path).expanduser()))
    resolved_root = lexical_root.resolve()
    resolved_output = lexical_output.resolve()
    if (
        lexical_output == lexical_root
        or not lexical_output.is_relative_to(lexical_root)
        or resolved_output == resolved_root
        or not resolved_output.is_relative_to(resolved_root)
    ):
        raise ValueError(f"output_outside_result_root:{resolved_output}")

    relative_parent = lexical_output.parent.relative_to(lexical_root)
    component = lexical_root
    for part in relative_parent.parts:
        component = component / part
        if component.exists() and component.is_symlink():
            raise ValueError(f"output_symlink_component:{component}")
    if lexical_root.is_symlink():
        raise ValueError(f"output_symlink_component:{lexical_root}")
    return resolved_output


def _as_rows(value: Any, *, field: str) -> list[list[float]]:
    if value is None:
        raise RuntimeError(f"missing_actual_telemetry:{field}")
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or not value:
        raise RuntimeError(f"actual_telemetry_shape_invalid:{field}")
    if not isinstance(value[0], (list, tuple)):
        value = [value]
    rows: list[list[float]] = []
    for raw_row in value:
        if not isinstance(raw_row, (list, tuple)) or not raw_row:
            raise RuntimeError(f"actual_telemetry_shape_invalid:{field}")
        try:
            rows.append([float(item) for item in raw_row])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"actual_telemetry_value_invalid:{field}") from exc
    return rows


def summarize_actual_telemetry(
    *, pid_value: Any, motor_values: Any, expected_motor_length: int
) -> dict[str, int | float]:
    """Summarize actual post-step PID and clipped motor telemetry.

    Extrema intentionally ignore non-finite samples.  When a channel group has
    no finite sample, both extrema use the finite ``0.0`` sentinel so the
    already-failed row remains strict-JSON evidence; ``nonfinite_count`` is the
    authoritative failure signal.
    """
    pid_rows = _as_rows(pid_value, field="_last_pid_value")
    motor_rows = _as_rows(
        motor_values, field="_last_motor_values_clipped"
    )
    if any(len(row) != 4 for row in pid_rows):
        raise RuntimeError("actual_telemetry_shape_invalid:_last_pid_value")
    if len(pid_rows) != len(motor_rows):
        raise RuntimeError("actual_telemetry_batch_mismatch")

    pid_flat = [value for row in pid_rows for value in row]
    motor_flat = [value for row in motor_rows for value in row]
    nonfinite_count = sum(
        not math.isfinite(value) for value in [*pid_flat, *motor_flat]
    )
    mismatch_count = sum(
        len(row) != int(expected_motor_length) for row in motor_rows
    )
    lengths = {len(row) for row in motor_rows}
    motor_vector_length = next(iter(lengths)) if len(lengths) == 1 else -1
    finite_pid = [value for value in pid_flat if math.isfinite(value)]
    finite_motor = [value for value in motor_flat if math.isfinite(value)]

    def finite_extrema(values: list[float]) -> tuple[float, float]:
        return (min(values), max(values)) if values else (0.0, 0.0)

    action_min, action_max = finite_extrema(finite_pid)
    motor_min, motor_max = finite_extrema(finite_motor)
    return {
        "action_min": action_min,
        "action_max": action_max,
        "motor_min": motor_min,
        "motor_max": motor_max,
        "motor_vector_length": motor_vector_length,
        "nonfinite_count": int(nonfinite_count),
        "dimension_mismatch_count": int(mismatch_count),
    }


def normalize_isaac_sim_version(distribution_version: str) -> str:
    """Normalize installed ``isaacsim`` metadata to the validator's major.minor form."""
    match = re.match(r"^(\d+)\.(\d+)(?:\.|$)", str(distribution_version))
    if match is None:
        raise RuntimeError("isaac_sim_version_invalid")
    return f"{match.group(1)}.{match.group(2)}"


def build_runtime_provenance(
    *,
    isaac_sim_distribution: str,
    isaac_lab_distribution: str,
    isaac_lab_version_file: str,
    isaac_lab_release_tag: str,
    isaac_lab_release_commit: str,
    isaac_lab_repo_commit: str,
    isaac_lab_repo_parent_commit: str,
    isaac_lab_repo_patch_sha256: str,
    isaac_lab_repo_dirty_files: Iterable[str],
) -> dict[str, Any]:
    """Build version fields from the locked unchanged-server runtime state."""
    release_tag = str(isaac_lab_release_tag).strip()
    tag_match = _LAB_RELEASE_TAG_RE.fullmatch(release_tag)
    lab_release = tag_match.group(1) if tag_match else ""
    dirty_files = tuple(str(value) for value in isaac_lab_repo_dirty_files)
    if (
        lab_release != EXPECTED_ISAAC_LAB_VERSION
        or str(isaac_lab_distribution) != EXPECTED_ISAAC_LAB_DISTRIBUTION
        or str(isaac_lab_version_file).strip() != EXPECTED_ISAAC_LAB_VERSION
        or release_tag != EXPECTED_ISAAC_LAB_RELEASE_TAG
        or str(isaac_lab_release_commit) != EXPECTED_ISAAC_LAB_RELEASE_COMMIT
        or str(isaac_lab_repo_commit) != EXPECTED_ISAAC_LAB_REPO_COMMIT
        or str(isaac_lab_repo_parent_commit) != EXPECTED_ISAAC_LAB_RELEASE_COMMIT
        or str(isaac_lab_repo_patch_sha256) != EXPECTED_ISAAC_LAB_PATCH_SHA256
        or dirty_files != EXPECTED_ISAAC_LAB_DIRTY_FILES
    ):
        raise RuntimeError("isaac_lab_release_provenance_invalid")
    return {
        "actual_isaac_sim": normalize_isaac_sim_version(isaac_sim_distribution),
        "actual_isaac_lab": lab_release,
        "runtime_provenance": {
            "isaac_sim_distribution": str(isaac_sim_distribution),
            "isaac_lab_distribution": str(isaac_lab_distribution),
            "isaac_lab_version_file": str(isaac_lab_version_file).strip(),
            "isaac_lab_release_tag": release_tag,
            "isaac_lab_release_commit": str(isaac_lab_release_commit),
            "isaac_lab_repo_commit": str(isaac_lab_repo_commit),
            "isaac_lab_repo_parent_commit": str(isaac_lab_repo_parent_commit),
            "isaac_lab_repo_patch_sha256": str(isaac_lab_repo_patch_sha256),
            "isaac_lab_repo_dirty_files": list(dirty_files),
        },
    }


def _git_output(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    return completed.stdout.strip()


def _git_bytes(repository: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        shell=False,
    )
    return completed.stdout


def _find_isaaclab_root(module_file: str | Path) -> Path:
    for candidate in (Path(module_file).resolve(), *Path(module_file).resolve().parents):
        if candidate.is_dir() and (candidate / ".git").exists():
            return candidate
    raise RuntimeError("isaac_lab_repository_not_found")


def detect_runtime_provenance(isaaclab_module_file: str | Path) -> dict[str, Any]:
    """Read and bind the exact unchanged-server IsaacLab repository state."""
    lab_root = _find_isaaclab_root(isaaclab_module_file)
    try:
        commit = _git_output(lab_root, "rev-parse", "HEAD")
        commit_object = _git_output(lab_root, "cat-file", "-p", "HEAD")
        parents = [
            line.split(maxsplit=1)[1]
            for line in commit_object.splitlines()
            if line.startswith("parent ")
        ]
        if len(parents) != 1:
            raise RuntimeError("isaac_lab_release_provenance_invalid")
        staged = _git_output(lab_root, "diff", "--cached", "--name-only")
        untracked = _git_output(
            lab_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        untracked = "\n".join(
            line[3:] for line in untracked.splitlines() if line.startswith("?? ")
        )
        if staged or untracked:
            raise RuntimeError("isaac_lab_release_provenance_invalid")
        dirty_files = tuple(
            _git_output(lab_root, "diff", "--name-only").splitlines()
        )
        patch_sha256 = hashlib.sha256(
            _git_bytes(lab_root, "diff", "--binary")
        ).hexdigest()
        version_file = (lab_root / "VERSION").read_text(encoding="utf-8").strip()
        sim_distribution = metadata.version("isaacsim")
        lab_distribution = metadata.version("isaaclab")
    except (
        OSError,
        subprocess.CalledProcessError,
        metadata.PackageNotFoundError,
    ) as exc:
        raise RuntimeError("runtime_version_provenance_unavailable") from exc
    return build_runtime_provenance(
        isaac_sim_distribution=sim_distribution,
        isaac_lab_distribution=lab_distribution,
        isaac_lab_version_file=version_file,
        isaac_lab_release_tag=EXPECTED_ISAAC_LAB_RELEASE_TAG,
        isaac_lab_release_commit=EXPECTED_ISAAC_LAB_RELEASE_COMMIT,
        isaac_lab_repo_commit=commit,
        isaac_lab_repo_parent_commit=parents[0],
        isaac_lab_repo_patch_sha256=patch_sha256,
        isaac_lab_repo_dirty_files=dirty_files,
    )


def _repository_commit() -> str:
    try:
        tracked_status = _git_output(
            PROJECT_ROOT, "status", "--porcelain=v1", "--untracked-files=no"
        )
        commit = _git_output(PROJECT_ROOT, "rev-parse", "HEAD")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("source_commit_unavailable") from exc
    if tracked_status:
        raise RuntimeError("source_worktree_tracked_dirty")
    if not _GIT_COMMIT_RE.fullmatch(commit):
        raise RuntimeError("source_commit_invalid")
    return commit


def _atomic_write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    result_root: str | Path | None = None,
) -> None:
    if result_root is not None:
        path = _revalidate_confined_output(path, result_root)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(payload, stream, allow_nan=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _empty_row(configuration: str, seed: int) -> dict[str, Any]:
    topology = qualification_record(configuration)
    return {
        "configuration": configuration,
        "thruster_count": topology["thruster_count"],
        "control_channels": list(topology["control_channels"]),
        "control_mask": list(topology["control_mask"]),
        "declared_control_rank": topology["declared_control_rank"],
        "environment_created": False,
        "reset_passed": False,
        "steps_completed": 0,
        "action_min": 0.0,
        "action_max": 0.0,
        "motor_min": 0.0,
        "motor_max": 0.0,
        "motor_vector_length": topology["thruster_count"],
        "nonfinite_count": 0,
        "dimension_mismatch_count": 0,
        "seed": seed,
        "status": "fail",
        "reason_codes": [],
    }


def _preflight_failure_payload(
    args: argparse.Namespace, reason: str
) -> dict[str, Any]:
    """Build evidence that is explicitly ineligible for exact-eight merging."""
    row = _empty_row(args.configuration, args.seed)
    _record_failure(row, reason)
    return {
        "artifact_kind": "preflight_failure",
        "eligible_for_merge": False,
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "evidence_level": "server_preflight_failure",
        "expected_isaac_sim": EXPECTED_ISAAC_SIM_VERSION,
        "expected_isaac_lab": EXPECTED_ISAAC_LAB_VERSION,
        "actual_isaac_sim": "",
        "actual_isaac_lab": "",
        "task_id": args.task,
        "results": [row],
    }


def _record_failure(row: dict[str, Any], reason: str) -> None:
    row["status"] = "fail"
    row["reason_codes"].append(reason.split(":", 1)[0])


def _close_runtime(env: Any, simulation_app: Any) -> list[str]:
    """Close both runtime layers and return stable, serializable reason codes."""
    failures: list[str] = []
    try:
        if env is not None:
            env.close()
    except Exception:
        failures.append("environment_close_failed")
    finally:
        try:
            simulation_app.close()
        except Exception:
            failures.append("simulation_app_close_failed")
    return failures


def _close_environment(env: Any) -> list[str]:
    """Close Gym without letting Kit shutdown preempt artifact persistence."""
    if env is None:
        return []
    try:
        env.close()
    except Exception:
        return ["environment_close_failed"]
    return []


def _persist_before_simulation_shutdown(
    output: Path,
    payload: dict[str, Any],
    result_root: Path,
    simulation_app: Any,
) -> None:
    """Persist and flush the row before Isaac Sim may terminate the process."""
    _atomic_write_json(output, payload, result_root=result_root)
    row = payload["results"][0]
    print(f"qualification_row={output}", flush=True)
    print(f"configuration={row['configuration']}", flush=True)
    print(f"status={row['status']}", flush=True)
    simulation_app.close()


def _record_cleanup_failures(
    payload: dict[str, Any], failures: Iterable[str], *, exit_code: int
) -> int:
    reasons = list(failures)
    if not reasons:
        return exit_code
    results = payload.get("results")
    if isinstance(results, list) and len(results) == 1 and isinstance(results[0], dict):
        for reason in reasons:
            _record_failure(results[0], reason)
    return 1


def _merge_step_summary(
    row: dict[str, Any], summary: dict[str, int | float], *, first_step: bool
) -> None:
    for prefix in ("action", "motor"):
        minimum = f"{prefix}_min"
        maximum = f"{prefix}_max"
        row[minimum] = summary[minimum] if first_step else min(row[minimum], summary[minimum])
        row[maximum] = summary[maximum] if first_step else max(row[maximum], summary[maximum])
    row["motor_vector_length"] = summary["motor_vector_length"]
    row["nonfinite_count"] += summary["nonfinite_count"]
    row["dimension_mismatch_count"] += summary["dimension_mismatch_count"]


def run_isaac_qualification(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    """Launch Isaac, execute one configuration, and return its row artifact."""
    # AppLauncher must exist and start before Gym, Torch, task, or environment imports.
    from isaaclab_app import AppLauncher

    app_launcher = AppLauncher({"headless": bool(args.headless)})
    simulation_app = app_launcher.app
    env = None
    payload: dict[str, Any] | None = None
    exit_code = 1
    preflight_error: Exception | None = None
    try:
        import gymnasium as gym
        import isaaclab
        import torch

        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg

        register_gym_tasks()

        provenance = detect_runtime_provenance(isaaclab.__file__)
        source_commit = _repository_commit()
        row = _empty_row(args.configuration, args.seed)
        topology = qualification_record(args.configuration)

        try:
            env_cfg = EasyUUVEnvCfg()
            env_cfg.scene.num_envs = args.num_envs
            if hasattr(env_cfg, "seed"):
                env_cfg.seed = args.seed
            env = gym.make(args.task, cfg=env_cfg)
            row["environment_created"] = True
            if args.configuration != "base":
                env.unwrapped.apply_embodiment_config(args.configuration)
            env.reset(seed=args.seed)
            row["reset_passed"] = True

            for step in range(args.steps):
                action_values = deterministic_excitation(step, topology["control_mask"])
                action = torch.tensor(
                    action_values,
                    dtype=torch.float32,
                    device=env.unwrapped.device,
                ).repeat(args.num_envs, 1)
                env.step(action)
                summary = summarize_actual_telemetry(
                    pid_value=getattr(env.unwrapped, "_last_pid_value", None),
                    motor_values=getattr(
                        env.unwrapped, "_last_motor_values_clipped", None
                    ),
                    expected_motor_length=topology["thruster_count"],
                )
                _merge_step_summary(row, summary, first_step=step == 0)
                row["steps_completed"] += 1
                if summary["nonfinite_count"]:
                    raise RuntimeError("nonfinite_actual_telemetry")
                if summary["dimension_mismatch_count"]:
                    raise RuntimeError("motor_dimension_mismatch")
            row["status"] = "pass"
        except Exception as exc:
            print(
                f"ERROR: environment_execution_failed:{type(exc).__name__}:{exc}",
                file=sys.stderr,
                flush=True,
            )
            _record_failure(row, str(exc) or type(exc).__name__)

        payload = {
            "schema_version": QUALIFICATION_SCHEMA_VERSION,
            "evidence_level": SERVER_EVIDENCE_LEVEL,
            "expected_isaac_sim": EXPECTED_ISAAC_SIM_VERSION,
            "expected_isaac_lab": EXPECTED_ISAAC_LAB_VERSION,
            "actual_isaac_sim": provenance["actual_isaac_sim"],
            "actual_isaac_lab": provenance["actual_isaac_lab"],
            "runtime_provenance": provenance["runtime_provenance"],
            "task_id": args.task,
            "source_commit": source_commit,
            "results": [row],
        }
        exit_code = 0 if row["status"] == "pass" else 1
    except Exception as exc:
        preflight_error = exc
        payload = _preflight_failure_payload(args, str(exc) or type(exc).__name__)
        exit_code = 1
    finally:
        cleanup_failures = _close_environment(env)
        if cleanup_failures:
            print(
                "ERROR: runtime_cleanup_failed:" + ",".join(cleanup_failures),
                file=sys.stderr,
            )
            if payload is not None:
                exit_code = _record_cleanup_failures(
                    payload, cleanup_failures, exit_code=exit_code
                )
        if payload is not None:
            output = resolve_output_path(args.output_json, args.result_root)
            if preflight_error is not None:
                print(f"ERROR: {preflight_error}", file=sys.stderr, flush=True)
            _persist_before_simulation_shutdown(
                output, payload, args.result_root, simulation_app
            )
        else:
            simulation_app.close()
    if payload is None:  # An earlier exception normally propagates through finally.
        raise RuntimeError("qualification_payload_unavailable")
    if preflight_error is not None:
        raise RuntimeError(str(preflight_error)) from preflight_error
    return payload, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    output: Path | None = None
    try:
        output = resolve_output_path(args.output_json, args.result_root)
        payload, exit_code = run_isaac_qualification(args)
        if not output.is_file():
            _atomic_write_json(output, payload, result_root=args.result_root)
    except (OSError, RuntimeError, ValueError) as exc:
        if output is not None:
            try:
                _atomic_write_json(
                    output,
                    _preflight_failure_payload(args, str(exc) or type(exc).__name__),
                    result_root=args.result_root,
                )
            except (OSError, RuntimeError, ValueError) as write_exc:
                print(f"ERROR: preflight_evidence_write_failed:{write_exc}", file=sys.stderr)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"qualification_row={output}")
    print(f"configuration={args.configuration}")
    print(f"status={payload['results'][0]['status']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
