"""Collect one strict Koopman-v2 episode from a real EasyUUV runtime.

The public parser and deterministic action schedule stay Isaac-free.  Isaac,
Gym and Torch are imported only after :class:`AppLauncher` starts in
``run_isaac_collection``.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.schema_v2 import (
    KOOPMAN_EPISODE_MANIFEST_V1,
    KOOPMAN_TRANSITION_SCHEMA_V2,
    SERVER_EVIDENCE_LEVEL,
    validate_episode_artifact_v2,
    validate_episode_v2,
    validate_transition_v2,
)
from workflows.koopman_bridge_v2 import KoopmanBridgeV2


TOPOLOGY_CONFIGURATIONS = ("base", "uuv6", "uuv4")
MINIMUM_TRANSITIONS = 8
DEFAULT_RESULT_ROOT = PROJECT_ROOT / "source" / "results" / "koopman_phase7"
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _minimum_steps(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("steps must be an integer") from exc
    if parsed < MINIMUM_TRANSITIONS:
        raise argparse.ArgumentTypeError(
            f"steps must be at least {MINIMUM_TRANSITIONS}"
        )
    return parsed


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect one real EasyUUV Koopman schema-v2 smoke episode."
    )
    parser.add_argument(
        "--configuration", required=True, choices=TOPOLOGY_CONFIGURATIONS
    )
    parser.add_argument("--steps", type=_minimum_steps, default=MINIMUM_TRANSITIONS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--task", default="EasyUUV-Direct-v1")
    parser.add_argument("--scenario", default="phase7-server-smoke")
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--controller-mode", default="legacy/Ssurface")
    parser.add_argument("--result-root", required=True, type=Path)
    parser.add_argument("--output-jsonl", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--failure-json", required=True, type=Path)
    parser.add_argument("--headless", action="store_true")
    return parser


def deterministic_action(step: int, configuration: str) -> tuple[float, ...]:
    """Exercise all four raw channels, including yaw for underactuated uuv4."""
    if configuration not in TOPOLOGY_CONFIGURATIONS:
        raise ValueError(f"configuration_unknown:{configuration}")
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise ValueError("step_invalid")
    channel = step % 4
    amplitude = 0.2 if (step // 4) % 2 == 0 else -0.2
    action = [0.0, 0.0, 0.0, 0.0]
    action[channel] = amplitude
    return tuple(action)


def _reject_symlink_components(path: Path, root: Path) -> None:
    component = root
    if component.exists() and component.is_symlink():
        raise ValueError(f"output_symlink_component:{component}")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"output_outside_result_root:{path}") from exc
    for part in relative.parts[:-1]:
        component = component / part
        if component.exists() and component.is_symlink():
            raise ValueError(f"output_symlink_component:{component}")


def resolve_output_path(output_path: str | Path, result_root: str | Path) -> Path:
    """Confine a fresh output below an explicit root and reject symlinks."""
    lexical_root = Path(os.path.abspath(Path(result_root).expanduser()))
    lexical_output = Path(os.path.abspath(Path(output_path).expanduser()))
    if lexical_output == lexical_root or not lexical_output.is_relative_to(lexical_root):
        raise ValueError(f"output_outside_result_root:{lexical_output}")
    _reject_symlink_components(lexical_output, lexical_root)
    resolved_root = lexical_root.resolve()
    resolved_output = lexical_output.resolve()
    if resolved_output == resolved_root or not resolved_output.is_relative_to(resolved_root):
        raise ValueError(f"output_outside_result_root:{resolved_output}")
    if lexical_output.exists():
        raise ValueError(f"artifact_exists:{lexical_output}")
    lexical_output.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(lexical_output, lexical_root)
    if lexical_output.exists():
        raise ValueError(f"artifact_exists:{lexical_output}")
    return lexical_output.resolve()


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise ValueError(f"artifact_exists:{path}")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class ServerEpisodeLoggerV2:
    """Fresh server-only episode writer with strict finalize-before-promotion."""

    def __init__(
        self,
        jsonl_path: Path,
        manifest_path: Path,
        *,
        runtime_provenance: Mapping[str, Any],
    ) -> None:
        self.path = jsonl_path
        self.manifest_path = manifest_path
        self.part_path = jsonl_path.with_name(f"{jsonl_path.name}.part")
        if any(path.exists() for path in (self.path, self.manifest_path, self.part_path)):
            raise ValueError("artifact_exists")
        self.runtime_provenance = dict(runtime_provenance)
        self._records: list[dict[str, Any]] = []
        self._stream = self.part_path.open("xb")
        self._finalized = False

    def write(self, record: Mapping[str, Any]) -> None:
        if self._finalized or self._stream.closed:
            raise ValueError("logger_closed")
        validate_transition_v2(record)
        if record["episode_provenance"]["evidence_level"] != SERVER_EVIDENCE_LEVEL:
            raise ValueError("server_evidence_required")
        copied = json.loads(json.dumps(record, allow_nan=False))
        self._stream.write(_canonical_json_bytes(copied))
        self._stream.flush()
        self._records.append(copied)

    def finalize(self) -> dict[str, Any]:
        if self._finalized or self._stream.closed:
            raise ValueError("logger_closed")
        summary = validate_episode_v2(self._records)
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        transition_bytes = self.part_path.read_bytes()
        manifest = {
            "manifest_version": KOOPMAN_EPISODE_MANIFEST_V1,
            "transition_schema_version": KOOPMAN_TRANSITION_SCHEMA_V2,
            "transition_file": self.path.name,
            "transition_sha256": hashlib.sha256(transition_bytes).hexdigest(),
            "record_count": summary["record_count"],
            "first_step_index": summary["first_step_index"],
            "last_step_index": summary["last_step_index"],
            "first_simulation_time_s": summary["first_simulation_time_s"],
            "last_simulation_time_s": summary["last_simulation_time_s"],
            "episode_invariants": summary["episode_invariants"],
            "platform_context_sha256": summary["platform_context_sha256"],
            "runtime_provenance": self.runtime_provenance,
            "evidence_level": SERVER_EVIDENCE_LEVEL,
        }
        manifest_bytes = _canonical_json_bytes(manifest)
        manifest_temp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.manifest_path.parent,
                prefix=f".{self.manifest_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                manifest_temp = Path(stream.name)
                stream.write(manifest_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists() or self.manifest_path.exists():
                raise ValueError("artifact_exists")
            os.replace(self.part_path, self.path)
            os.replace(manifest_temp, self.manifest_path)
            validate_episode_artifact_v2(self.path, self.manifest_path)
        finally:
            if manifest_temp is not None and manifest_temp.exists():
                manifest_temp.unlink()
        self._finalized = True
        return manifest


def collect_episode_with_bridge(
    *,
    bridge: Any,
    logger: Any,
    configuration: str,
    steps: int,
    provenance: Mapping[str, Any],
    action_builder: Callable[[tuple[float, ...]], Any] | None = None,
) -> dict[str, Any]:
    """Drive exactly ``steps`` Bridge calls and finalize only after all pass."""
    if configuration not in TOPOLOGY_CONFIGURATIONS:
        raise ValueError(f"configuration_unknown:{configuration}")
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < MINIMUM_TRANSITIONS:
        raise ValueError(f"steps_below_minimum:{steps}")
    if provenance.get("evidence_level") not in {
        "local_contract",
        SERVER_EVIDENCE_LEVEL,
    }:
        raise ValueError("evidence_level_invalid")
    for step in range(steps):
        action = deterministic_action(step, configuration)
        action_input = action if action_builder is None else action_builder(action)
        record = bridge.step_and_record(action_input)
        logger.write(record)
    return logger.finalize()


def _repository_commit(allowed_untracked_root: str | Path) -> str:
    """Bind HEAD while allowing only this run's explicit in-repo evidence root."""
    project_root = Path(os.path.abspath(PROJECT_ROOT))
    allowed_root = Path(os.path.abspath(Path(allowed_untracked_root).expanduser()))
    allowed_is_in_project = (
        allowed_root != project_root and allowed_root.is_relative_to(project_root)
    )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    for entry in status.stdout.split("\0"):
        if not entry:
            continue
        if not entry.startswith("?? "):
            raise RuntimeError("source_worktree_tracked_dirty")
        untracked = Path(os.path.abspath(project_root / entry[3:]))
        if not allowed_is_in_project or not untracked.is_relative_to(allowed_root):
            raise RuntimeError("source_worktree_untracked_dirty")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if not _COMMIT_RE.fullmatch(commit):
        raise RuntimeError("source_commit_invalid")
    return commit


def _failure_payload(args: argparse.Namespace, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "easyuuv-koopman-collection-failure-v1",
        "configuration": args.configuration,
        "episode_id": args.episode_id,
        "reason": reason,
        "eligible_for_merge": False,
    }


def run_isaac_collection(args: argparse.Namespace) -> int:
    """Launch Isaac and create one server episode; never synthesize telemetry."""
    # AppLauncher must start before Gym, Torch, task, or environment imports.
    from isaaclab_app import AppLauncher

    app_launcher = AppLauncher({"headless": bool(args.headless)})
    simulation_app = app_launcher.app
    env = None
    try:
        import gymnasium as gym
        import isaaclab
        import torch

        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance

        source_commit = _repository_commit(args.result_root)
        provenance = detect_runtime_provenance(isaaclab.__file__)
        runtime = dict(provenance["runtime_provenance"])
        runtime.update(
            {
                "artifact_origin": SERVER_EVIDENCE_LEVEL,
                "actual_isaac_sim": provenance["actual_isaac_sim"],
                "actual_isaac_lab": provenance["actual_isaac_lab"],
                "native_status": 0,
                "tee_status": 0,
                "semantic_status": "pass",
                "wrench_source": "post_actuator_thruster_only",
                "context_source": "same_step_oracle_snapshot",
            }
        )
        register_gym_tasks()
        cfg = EasyUUVEnvCfg()
        cfg.scene.num_envs = 1
        if hasattr(cfg, "seed"):
            cfg.seed = args.seed
        env = gym.make(args.task, cfg=cfg)
        if args.configuration != "base":
            env.unwrapped.apply_embodiment_config(args.configuration)
        env.reset(seed=args.seed)
        control_dt = float(getattr(env.unwrapped, "step_dt", 0.0))
        if control_dt <= 0.0:
            raise RuntimeError("control_dt_unavailable")
        bridge = KoopmanBridgeV2(
            env=env,
            env_index=0,
            configuration=args.configuration,
            scenario=args.scenario,
            episode_id=args.episode_id,
            seed=args.seed,
            task_id=args.task,
            controller_mode=args.controller_mode,
            source_commit=source_commit,
            evidence_level=SERVER_EVIDENCE_LEVEL,
            control_dt_s=control_dt,
        )
        logger = ServerEpisodeLoggerV2(
            args.output_jsonl,
            args.output_manifest,
            runtime_provenance=runtime,
        )
        collect_episode_with_bridge(
            bridge=bridge,
            logger=logger,
            configuration=args.configuration,
            steps=args.steps,
            provenance={"evidence_level": SERVER_EVIDENCE_LEVEL},
            action_builder=lambda action: torch.tensor(
                [action], dtype=torch.float32, device=env.unwrapped.device
            ),
        )
        return 0
    finally:
        if env is not None:
            env.close()
        simulation_app.close()


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    failure_path: Path | None = None
    reason: str | None = None
    try:
        failure_path = resolve_output_path(args.failure_json, args.result_root)
        args.output_jsonl = resolve_output_path(args.output_jsonl, args.result_root)
        args.output_manifest = resolve_output_path(args.output_manifest, args.result_root)
        if len({failure_path, args.output_jsonl, args.output_manifest}) != 3:
            raise ValueError("output_path_collision")
        args.failure_json = failure_path
        return run_isaac_collection(args)
    except SystemExit as exc:
        reason = f"unexpected_system_exit:{exc.code}"
    except Exception as exc:
        reason = str(exc) or type(exc).__name__
    try:
        if failure_path is not None and not failure_path.exists():
            _atomic_write_bytes(
                failure_path,
                _canonical_json_bytes(_failure_payload(args, reason)),
            )
    except (OSError, ValueError) as write_error:
        print(f"ERROR: failure_evidence_write_failed:{write_error}", file=sys.stderr)
    print(f"ERROR: {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
