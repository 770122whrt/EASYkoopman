"""D-23-guarded Phase 8.1 identification collector entrypoint.

Authorization is checked before importing Isaac, the v2.1 bridge/schema, or
touching a result root.  This local repair deliberately does not execute it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.d23_approval_v21 import require_canonical_d23_approval_v21


_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _validate_collection_protocol_contract(
    role_payload: dict[str, Any], *, expected_evidence_level: str
) -> str:
    """Bind collection semantics to the pending role protocol before Isaac starts."""

    if (
        role_payload.get("artifact_origin_level") != expected_evidence_level
        or role_payload.get("actuator_memory_initial_value_4")
        != [0.0, 0.0, 0.0, 0.0]
        or role_payload.get("unrecorded_warmup_control_intervals") != 0
    ):
        raise ValueError("collection_protocol_contract_mismatch")
    return expected_evidence_level


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Phase 8.1 v2.1 episodes.")
    parser.add_argument("--approval-record", required=True, type=Path)
    parser.add_argument("--role-protocol", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--configuration")
    parser.add_argument(
        "--source-commit",
        help="Optional expected commit; the recorded commit is always derived from clean HEAD.",
    )
    parser.add_argument("--headless", action="store_true")
    return parser


def _repository_commit(*, expected_source_commit: str | None = None) -> str:
    """Return clean repository HEAD and optionally bind it to an expected commit."""
    try:
        status = subprocess.run(
            [
                "git",
                "-c",
                "core.excludesFile=",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        for item in status.stdout.split("\0"):
            if not item:
                continue
            if item.startswith("?? "):
                raise RuntimeError("source_worktree_untracked_dirty")
            raise RuntimeError("source_worktree_tracked_dirty")
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("source_commit_unavailable") from exc
    source_commit = result.stdout.strip()
    if not _COMMIT_RE.fullmatch(source_commit):
        raise RuntimeError("source_commit_invalid")
    if expected_source_commit is not None:
        if not _COMMIT_RE.fullmatch(expected_source_commit):
            raise RuntimeError("expected_source_commit_invalid")
        if expected_source_commit != source_commit:
            raise RuntimeError("source_commit_mismatch")
    return source_commit


def _run_authorized_collection(**kwargs: Any) -> int:
    """Run one configuration matrix after exact D-23 authorization."""
    # AppLauncher and every simulator/data writer import intentionally occur
    # after main() validates the approval binding and clean source identity.
    args = kwargs["args"]
    source_commit = kwargs["source_commit"]
    from koopman.d23_approval_v21 import (
        PUBLIC_CONFIGURATIONS_V21,
        validate_role_protocol_proposal_v21,
    )
    from koopman.schema_v2 import SERVER_EVIDENCE_LEVEL

    if args.configuration not in PUBLIC_CONFIGURATIONS_V21:
        raise ValueError("configuration_required")
    role_payload = json.loads(args.role_protocol.read_text(encoding="utf-8"))
    validate_role_protocol_proposal_v21(role_payload)
    evidence_level = _validate_collection_protocol_contract(
        role_payload, expected_evidence_level=SERVER_EVIDENCE_LEVEL
    )
    entries = [
        dict(entry)
        for entry in role_payload["entries"]
        if entry["configuration"] == args.configuration
    ]
    if len(entries) != 12:
        raise ValueError("role_protocol_configuration_entry_count")

    from isaaclab_app import AppLauncher

    app_launcher = AppLauncher({"headless": bool(args.headless)})
    simulation_app = app_launcher.app
    env = None
    failed = False
    try:
        import gymnasium as gym
        import isaaclab
        import torch

        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg
        from koopman.schema_v21 import KoopmanEpisodeLoggerV21
        from workflows.collect_koopman_v2_identification import (
            _close_simulation_app,
            collect_policy_entries,
            deterministic_policy_action,
            resolve_output_path,
            write_episode_success_logs,
        )
        from workflows.koopman_bridge_v21 import KoopmanBridgeV21
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance

        register_gym_tasks()
        cfg = EasyUUVEnvCfg()
        cfg.scene.num_envs = 1
        contract = role_payload["environment_contract"]
        cfg.cap_episode_length = False
        cfg.eval_mode = contract["eval_mode"]
        cfg.reference_mode = contract["reference_mode"]
        cfg.disturbance_cfg.mode = contract["disturbance_mode"]
        cfg.noise_cfg.enable_noise = contract["sensor_noise_enabled"]
        cfg.domain_randomization.use_custom_randomization = contract[
            "domain_randomization_enabled"
        ]
        env = gym.make(role_payload["task_id"], cfg=cfg)
        if args.configuration != "base":
            env.unwrapped.apply_embodiment_config(args.configuration)

        timing = role_payload["timing_contract"]
        physics_dt_s = float(env.unwrapped.sim.cfg.dt)
        decimation = int(env.unwrapped.cfg.decimation)
        control_dt_s = float(getattr(env.unwrapped, "step_dt", 0.0))
        if (
            physics_dt_s != timing["physics_dt_s"]
            or decimation != timing["decimation"]
            or control_dt_s != timing["control_dt_s"]
        ):
            raise RuntimeError("runtime_timing_contract_mismatch")

        provenance = detect_runtime_provenance(isaaclab.__file__)
        runtime = dict(provenance["runtime_provenance"])
        runtime.update(
            {
                "actual_isaac_lab": provenance["actual_isaac_lab"],
                "actual_isaac_sim": provenance["actual_isaac_sim"],
                "artifact_origin": evidence_level,
                "generator": "collect_koopman_v21_identification",
                "semantic_status": "pass",
            }
        )
        output_root = args.output_root.resolve()
        if output_root.exists() or output_root.is_symlink():
            raise ValueError(f"output_root_exists:{output_root}")
        output_root.mkdir(parents=True)

        def reset(seed: int, episode_id: str) -> None:
            del episode_id
            env.reset(seed=seed)

        def bridge_factory(entry: dict[str, Any]) -> KoopmanBridgeV21:
            return KoopmanBridgeV21(
                env=env,
                env_index=0,
                configuration=args.configuration,
                scenario=entry["scenario"],
                episode_id=entry["episode_id"],
                seed=entry["seed"],
                task_id=role_payload["task_id"],
                controller_mode=role_payload["controller_mode"],
                source_commit=source_commit,
                evidence_level=evidence_level,
                physics_dt_s=physics_dt_s,
                decimation=decimation,
                control_dt_s=control_dt_s,
            )

        def logger_factory(entry: dict[str, Any]) -> KoopmanEpisodeLoggerV21:
            episode = resolve_output_path(
                output_root / entry["transition_path"], output_root
            )
            manifest = resolve_output_path(
                output_root / entry["manifest_path"], output_root
            )
            return KoopmanEpisodeLoggerV21(
                episode,
                manifest_path=manifest,
                runtime_provenance=runtime,
            )

        results = collect_policy_entries(
            entries,
            reset=reset,
            bridge_factory=bridge_factory,
            logger_factory=logger_factory,
            action_builder=lambda action: torch.tensor(
                [action], dtype=torch.float32, device=env.unwrapped.device
            ),
        )
        # Exercise the exact registered action generator before recording a
        # success log; collect_policy_entries invokes the same function.
        deterministic_policy_action(entries[0], 0)
        write_episode_success_logs(output_root, entries, results)
        return 0
    except BaseException:
        failed = True
        raise
    finally:
        if env is not None:
            env.close()
        if "_close_simulation_app" in locals():
            _close_simulation_app(simulation_app, collection_failed=failed)
        else:
            simulation_app.close()


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        approval = require_canonical_d23_approval_v21(
            args.approval_record,
            role_protocol_path=args.role_protocol,
            analysis_policy_path=args.analysis_policy,
        )
        source_commit = _repository_commit(expected_source_commit=args.source_commit)
        return int(
            _run_authorized_collection(
                args=args,
                approval=approval,
                source_commit=source_commit,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
