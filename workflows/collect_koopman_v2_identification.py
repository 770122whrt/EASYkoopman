"""Collect the two pre-registered Phase 8 pilot episodes for one configuration.

The public parser, policy action generator and collection loop remain Isaac-free.
Isaac, Gym and Torch are imported only after :class:`AppLauncher` starts.
This module performs collection only and deliberately imports no model fitting or
evaluation code.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.protocol_v2 import (
    PILOT_CONTROLLER_MODE,
    PILOT_RAW_ACTION_ABS_MAX,
    PILOT_TASK_ID,
    PUBLIC_CONFIGURATIONS,
)
from koopman.schema_v2 import SERVER_EVIDENCE_LEVEL
from workflows.collect_koopman_v2_smoke import (
    ServerEpisodeLoggerV2,
    _atomic_write_bytes,
    _canonical_json_bytes,
)
from workflows.koopman_bridge_v2 import KoopmanBridgeV2
from workflows.validate_phase8_pilot_policy import load_operational_pilot_policy


DEFAULT_RESULT_ROOT = PROJECT_ROOT / "source" / "results" / "koopman_phase8_pilot"
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect two exact-policy Phase 8 identification-pilot episodes."
    )
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--configuration", required=True, choices=PUBLIC_CONFIGURATIONS)
    parser.add_argument("--result-root", required=True, type=Path)
    parser.add_argument("--headless", action="store_true")
    return parser


def deterministic_policy_action(
    entry: Mapping[str, Any], step: int
) -> tuple[float, float, float, float]:
    """Return the registered bounded raw action without reading trajectories."""
    if isinstance(step, bool) or not isinstance(step, int) or not 0 <= step < 128:
        raise ValueError(f"step_invalid:{step}")
    kind = entry.get("policy_kind")
    seed = entry.get("seed")
    if kind == "axis_pulse" and seed == 8101:
        channel = (step // 8) % 4
        sign = 1.0 if (step // 32) % 2 == 0 else -1.0
        action = [0.0, 0.0, 0.0, 0.0]
        action[channel] = sign * PILOT_RAW_ACTION_ABS_MAX
        return tuple(action)  # type: ignore[return-value]
    if kind == "bounded_multisine" and seed == 8102:
        # Frequencies/phases are fixed functions of the registered seed.  The
        # formula is deterministic, bounded and independent of collected rows.
        values = []
        for channel in range(4):
            phase = ((seed + 37 * (channel + 1)) % 360) * math.pi / 180.0
            value = 0.12 * math.sin((step + 1) * (channel + 1) * 0.17 + phase)
            value += 0.08 * math.sin((step + 1) * (channel + 2) * 0.071 - phase)
            values.append(value)
        return tuple(values)  # type: ignore[return-value]
    raise ValueError(f"pilot_policy_invalid:entry_action:{kind}:{seed}")


def collect_policy_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    reset: Callable[[int, str], None],
    bridge_factory: Callable[[dict[str, Any]], Any],
    logger_factory: Callable[[dict[str, Any]], Any],
    action_builder: Callable[[tuple[float, ...]], Any] | None = None,
) -> list[dict[str, Any]]:
    """Reset, collect and finalize each policy episode independently."""
    if len(entries) != 2:
        raise ValueError(f"pilot_policy_invalid:configuration_entry_count:{len(entries)}")
    normalized = [dict(entry) for entry in entries]
    configurations = {entry.get("configuration") for entry in normalized}
    if len(configurations) != 1 or next(iter(configurations)) not in PUBLIC_CONFIGURATIONS:
        raise ValueError("pilot_policy_invalid:configuration_entry_set")
    results: list[dict[str, Any]] = []
    for entry in normalized:
        count = entry.get("transition_count")
        if isinstance(count, bool) or count != 128:
            raise ValueError("pilot_policy_invalid:transition_count")
        reset(entry["seed"], entry["episode_id"])
        bridge = bridge_factory(entry)
        logger = logger_factory(entry)
        for step in range(count):
            action = deterministic_policy_action(entry, step)
            action_input = action if action_builder is None else action_builder(action)
            record = bridge.step_and_record(action_input)
            logger.write(record)
        result = logger.finalize()
        if result.get("record_count") != count:
            raise ValueError(f"pilot_health_failed:transition_count:{entry['episode_id']}")
        results.append(dict(result))
    return results


def write_episode_success_logs(
    result_root: str | Path,
    entries: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
) -> list[Path]:
    """Persist one fresh collection-health log for every completed episode."""
    if len(entries) != 2 or len(results) != len(entries):
        raise ValueError("pilot_health_failed:success_log_result_count")
    root = Path(os.path.abspath(Path(result_root).expanduser()))
    written: list[Path] = []
    for entry_value, result_value in zip(entries, results, strict=True):
        entry = dict(entry_value)
        result = dict(result_value)
        episode_id = result.get("episode_id")
        invariants = result.get("episode_invariants")
        if episode_id is None and isinstance(invariants, Mapping):
            episode_id = invariants.get("episode_id")
        if episode_id != entry.get("episode_id"):
            raise ValueError("pilot_health_failed:success_log_episode_id")
        if result.get("record_count") != entry.get("transition_count"):
            raise ValueError("pilot_health_failed:success_log_record_count")
        path = resolve_output_path(
            root / "logs" / f"{entry['episode_id']}.log",
            root,
        )
        payload = (
            f"episode_id={entry['episode_id']}\n"
            f"configuration={entry['configuration']}\n"
            f"policy_kind={entry['policy_kind']}\n"
            f"seed={entry['seed']}\n"
            f"record_count={result['record_count']}\n"
            "semantic_status=pass\n"
        ).encode("utf-8")
        _atomic_write_bytes(path, payload)
        written.append(path)
    return written


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
    """Confine one fresh episode/manifest path below the explicit pilot root."""
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


def _repository_commit(allowed_untracked_roots: Sequence[str | Path]) -> str:
    """Bind clean tracked source while allowing only explicit evidence roots."""
    project_root = Path(os.path.abspath(PROJECT_ROOT))
    allowed = [
        Path(os.path.abspath(Path(value).expanduser())) for value in allowed_untracked_roots
    ]
    if any(root == project_root or not root.is_relative_to(project_root) for root in allowed):
        raise RuntimeError("source_worktree_untracked_root_invalid")
    status = subprocess.run(
        ["git", "-c", "core.excludesFile=", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    for item in status.stdout.split("\0"):
        if not item:
            continue
        if not item.startswith("?? "):
            raise RuntimeError("source_worktree_tracked_dirty")
        untracked = Path(os.path.abspath(project_root / item[3:]))
        if not any(untracked.is_relative_to(root) for root in allowed):
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


def _configuration_entries(policy: Mapping[str, Any], configuration: str) -> list[dict[str, Any]]:
    entries = [dict(entry) for entry in policy["entries"] if entry["configuration"] == configuration]
    if len(entries) != 2:
        raise ValueError(f"pilot_policy_invalid:configuration_entry_count:{configuration}")
    return entries


def _close_simulation_app(simulation_app: Any, *, collection_failed: bool) -> None:
    """Close Isaac without allowing its clean exit signal to mask collection state."""
    try:
        simulation_app.close()
    except SystemExit as exc:
        if collection_failed or exc.code in (None, 0):
            return
        raise


def run_isaac_collection(args: argparse.Namespace) -> int:
    """Launch one Isaac process and collect both registered episodes."""
    # AppLauncher must start before Gym, Torch, task, or environment imports.
    from isaaclab_app import AppLauncher

    app_launcher = AppLauncher({"headless": bool(args.headless)})
    simulation_app = app_launcher.app
    env = None
    collection_failed = False
    try:
        import gymnasium as gym
        import isaaclab
        import torch

        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance

        policy = load_operational_pilot_policy(args.policy)
        entries = _configuration_entries(policy, args.configuration)
        status_root = args.result_root.parent / "koopman_phase8_pilot_status"
        source_commit = _repository_commit((args.result_root, status_root))
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
        env = gym.make(PILOT_TASK_ID, cfg=cfg)
        if args.configuration != "base":
            env.unwrapped.apply_embodiment_config(args.configuration)
        control_dt = float(getattr(env.unwrapped, "step_dt", 0.0))
        if control_dt <= 0.0:
            raise RuntimeError("control_dt_unavailable")

        def reset(seed: int, episode_id: str) -> None:
            del episode_id
            env.reset(seed=seed)

        def bridge_factory(entry: dict[str, Any]) -> KoopmanBridgeV2:
            return KoopmanBridgeV2(
                env=env,
                env_index=0,
                configuration=args.configuration,
                scenario=entry["scenario"],
                episode_id=entry["episode_id"],
                seed=entry["seed"],
                task_id=PILOT_TASK_ID,
                controller_mode=PILOT_CONTROLLER_MODE,
                source_commit=source_commit,
                evidence_level=SERVER_EVIDENCE_LEVEL,
                control_dt_s=control_dt,
            )

        def logger_factory(entry: dict[str, Any]) -> ServerEpisodeLoggerV2:
            episode = resolve_output_path(
                args.result_root / "episodes" / f"{entry['episode_id']}.jsonl",
                args.result_root,
            )
            manifest = resolve_output_path(
                args.result_root / "manifests" / f"{entry['episode_id']}.manifest.json",
                args.result_root,
            )
            return ServerEpisodeLoggerV2(episode, manifest, runtime_provenance=runtime)

        results = collect_policy_entries(
            entries,
            reset=reset,
            bridge_factory=bridge_factory,
            logger_factory=logger_factory,
            action_builder=lambda action: torch.tensor(
                [action], dtype=torch.float32, device=env.unwrapped.device
            ),
        )
        write_episode_success_logs(args.result_root, entries, results)
        return 0
    except BaseException:
        collection_failed = True
        raise
    finally:
        if env is not None:
            env.close()
        _close_simulation_app(simulation_app, collection_failed=collection_failed)


def _failure_payload(args: argparse.Namespace, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "phase8-pilot-collection-failure-v1",
        "configuration": args.configuration,
        "reason": reason,
        "eligible_for_pilot_audit": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        args.result_root = Path(os.path.abspath(args.result_root))
        policy = load_operational_pilot_policy(args.policy)
        _configuration_entries(policy, args.configuration)
        args.result_root.mkdir(parents=True, exist_ok=True)
        return run_isaac_collection(args)
    except SystemExit as exc:
        reason = f"unexpected_system_exit:{exc.code}"
    except Exception as exc:
        reason = str(exc) or type(exc).__name__
    try:
        status_root = args.result_root.parent / "koopman_phase8_pilot_status"
        status_root.mkdir(parents=True, exist_ok=True)
        failure = status_root / f"{args.configuration}.failure.json"
        if not failure.exists():
            _atomic_write_bytes(failure, _canonical_json_bytes(_failure_payload(args, reason)))
    except (OSError, ValueError) as write_error:
        print(f"ERROR: failure_evidence_write_failed:{write_error}", file=sys.stderr)
    print(f"ERROR: {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
