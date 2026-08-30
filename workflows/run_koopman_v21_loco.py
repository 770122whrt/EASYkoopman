"""D-23-guarded formal Phase 8.1 LOCO entrypoint."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.d23_approval_v21 import require_canonical_d23_approval_v21


_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run formal Phase 8.1 LOCO.")
    parser.add_argument("--approval-record", required=True, type=Path)
    parser.add_argument("--role-protocol", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--split", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--fold", default="all")
    return parser


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _write_json(path: Path, value: Any) -> None:
    from koopman.evidence_v2 import canonical_json_bytes

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _default_formal_backend(
    args: argparse.Namespace, *, expected_evidence_level: str
) -> Any:
    """Build the first-party dataset backend lazily after authorization.

    The backend lives behind this seam so an Isaac-free contract test can feed
    synthetic numerical evidence while exercising the identical production
    orchestration and access state machine.
    """

    from koopman.evaluation_v21 import DatasetFormalLocoBackendV21

    return DatasetFormalLocoBackendV21(
        dataset_root=args.dataset_root,
        analysis_policy_path=args.analysis_policy,
        expected_source_commit=args.source_commit,
        expected_evidence_level=expected_evidence_level,
    )


def _run_authorized_loco(**kwargs: Any) -> int:
    """Execute all exact-eight folds after canonical D-23 authorization."""

    # Every import that can lead to dataset access stays below the D-23 call in main().
    from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
    from koopman.d23_approval_v21 import EXPERIMENT_ID_V21
    from koopman.evaluation_v21 import (
        ExpertEpisodeV21,
        FoldEvaluationSessionV21,
        FormalFoldSourceInputsV21,
        load_protocol_episode_registry_v21,
    )
    from koopman.loco_v21 import (
        build_source_candidate_ledger_v21,
        freeze_primary_v21,
        write_source_candidate_ledger_v21,
    )
    from koopman.selection_v21 import (
        BaselineOuterEvidenceV21,
        EligibleFamilyOuterEvidenceV21,
        EpisodeOuterEvidenceV21,
        FoldOuterEvidenceV21,
        fold_outer_evidence_to_dict_v21,
    )

    args = kwargs["args"]
    approval = kwargs["approval"]
    backend = kwargs.get("backend")
    required_paths = (args.role_protocol, args.analysis_policy, args.inventory, args.split)
    if any(path is None for path in required_paths) or args.dataset_root is None:
        raise ValueError("formal_loco_input_required")
    if not _COMMIT_RE.fullmatch(str(args.source_commit or "")):
        raise ValueError("source_commit_invalid")

    # Inventory and split are metadata-only. They are validated before a backend is
    # constructed or any transition/manifest path is opened.
    registry = load_protocol_episode_registry_v21(
        role_protocol_path=args.role_protocol,
        inventory_path=args.inventory,
    )
    registry.validate_split_path(args.split)
    policy_sha256 = _file_sha256(Path(args.analysis_policy))
    try:
        analysis_policy = json.loads(Path(args.analysis_policy).read_text(encoding="utf-8"))
        family_order = tuple(
            analysis_policy["inner_decision_algorithm"]["family_order"]
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("formal_loco_analysis_policy_invalid") from exc
    if (
        approval.get("decision") != "approved"
        or approval.get("experiment_id") != EXPERIMENT_ID_V21
        or approval.get("role_protocol_sha256") != registry.role_protocol_sha256
        or approval.get("analysis_policy_sha256") != policy_sha256
    ):
        raise ValueError("formal_loco_approval_binding_mismatch")

    output = Path(args.output_root).resolve()
    if output.exists() or output.is_symlink():
        raise ValueError(f"output_root_exists:{output}")
    staging = output.with_name(f".{output.name}.staging-{os.getpid()}")
    if staging.exists() or staging.is_symlink():
        raise ValueError(f"output_root_exists:{staging}")
    if backend is None:
        backend = _default_formal_backend(
            args, expected_evidence_level=registry.artifact_origin_level
        )
    staging.mkdir(parents=True)
    fold_evidence: list[FoldOuterEvidenceV21] = []
    try:
        for heldout in SUPPORTED_EMBODIMENTS:
            sources = tuple(value for value in SUPPORTED_EMBODIMENTS if value != heldout)
            fold_root = staging / "folds" / heldout
            source_inputs = backend.prepare_source_fold(
                heldout_configuration=heldout,
                source_configurations=sources,
                source_bindings=registry.source_non_test(heldout),
            )
            if not isinstance(source_inputs, FormalFoldSourceInputsV21):
                raise ValueError("formal_source_inputs_invalid")
            ledger = build_source_candidate_ledger_v21(
                source_inputs.candidate_evaluations,
                source_configurations=sources,
                expected_candidates=source_inputs.expected_candidates,
                family_order=family_order,
            )
            write_source_candidate_ledger_v21(
                ledger, fold_root / "source_candidate_ledger.json"
            )
            primary = freeze_primary_v21(ledger, frozen_at=_utc_now())
            if hasattr(backend, "bind_primary"):
                backend.bind_primary(
                    heldout_configuration=heldout,
                    primary=primary,
                )
            _write_json(fold_root / "pre_test_freeze.json", primary.to_dict())
            test_bindings = registry.for_configuration_role(heldout, "test")
            session = FoldEvaluationSessionV21(
                heldout,
                ledger,
                primary,
                test_episode_bindings=test_bindings,
                role_protocol_sha256=registry.role_protocol_sha256,
            )
            session.generate_heldout_descriptor_diagnostic(
                source_transform=source_inputs.source_transform,
                heldout_descriptor=backend.build_heldout_descriptor(
                    heldout_configuration=heldout
                ),
                output_path=fold_root / "heldout_descriptor_diagnostic.json",
            )
            expert_fit = tuple(
                ExpertEpisodeV21(
                    binding.episode_id,
                    heldout,
                    "fit",
                    backend.open_episode(binding),
                )
                for binding in registry.for_configuration_role(heldout, "fit")
            )
            expert_validation = tuple(
                ExpertEpisodeV21(
                    binding.episode_id,
                    heldout,
                    "validation",
                    backend.open_episode(binding),
                )
                for binding in registry.for_configuration_role(heldout, "validation")
            )
            expert = session.select_and_freeze_expert(
                candidates=backend.expert_candidates(
                    heldout_configuration=heldout
                ),
                fit_episodes=expert_fit,
                validation_episodes=expert_validation,
                fitter=backend.fit_expert,
                evaluator=backend.evaluate_expert,
                artifact_path=fold_root / "expert" / "selected_model.json",
                serializer=backend.serialize_expert,
                loader=backend.load_expert,
                identity_reader=backend.expert_identities,
            )
            _write_json(fold_root / "expert" / "expert_freeze.json", expert.to_dict())
            token = session.authorize_primary_test()
            opened_test = session.open_primary_test(
                token, opener=backend.open_episode
            )

            roles: dict[str, Any] = {}
            for role in ("persistence", "simple_linear", "pooled", "conditional"):
                if role in {"pooled", "conditional"} and role not in primary.model_identities:
                    roles[role] = EligibleFamilyOuterEvidenceV21(
                        family=role,
                        selection_eligible=True,
                        status="failed",
                        reason_code="source_candidate_unavailable",
                        episodes=(),
                    )
                    continue
                horizon_sets = tuple(
                    backend.evaluate_test_horizons(
                        heldout_configuration=heldout,
                        role=role,
                        model_identity=primary.model_identities.get(role),
                        opened_episodes=opened_test,
                    )
                )
                if len(horizon_sets) != 3:
                    raise ValueError("formal_test_evidence_count_mismatch")
                episodes = tuple(
                    EpisodeOuterEvidenceV21(binding, horizons)
                    for binding, horizons in zip(
                        test_bindings, horizon_sets, strict=True
                    )
                )
                roles[role] = (
                    BaselineOuterEvidenceV21(role, episodes)
                    if role in {"persistence", "simple_linear"}
                    else EligibleFamilyOuterEvidenceV21(
                        role,
                        True,
                        (
                            "failed"
                            if any(
                                horizon.status == "failed"
                                for episode in episodes
                                for horizon in episode.horizons.values()
                            )
                            else "success"
                        ),
                        (
                            "rollout_horizon_failed"
                            if any(
                                horizon.status == "failed"
                                for episode in episodes
                                for horizon in episode.horizons.values()
                            )
                            else None
                        ),
                        episodes,
                    )
                )
            fold = FoldOuterEvidenceV21(
                heldout_configuration=heldout,
                test_token=token,
                persistence=roles["persistence"],
                simple_linear=roles["simple_linear"],
                pooled=roles["pooled"],
                conditional=roles["conditional"],
            )
            fold_evidence.append(fold)
            _write_json(
                fold_root / "fold_outer_evidence.json",
                fold_outer_evidence_to_dict_v21(fold),
            )

        summary = {
            "analysis_policy_sha256": policy_sha256,
            "evaluation_version": "phase8.1-formal-loco-evaluation-v1",
            "experiment_id": EXPERIMENT_ID_V21,
            "folds": [
                fold_outer_evidence_to_dict_v21(fold) | {"state": "TEST_OPENED"}
                for fold in fold_evidence
            ],
            "inventory_sha256": registry.inventory_sha256,
            "role_protocol_sha256": registry.role_protocol_sha256,
            "source_commit": args.source_commit,
            "split_sha256": _file_sha256(Path(args.split)),
        }
        summary_path = staging / "evaluation_summary.json"
        _write_json(summary_path, summary)
        envelope = {
            "analysis_policy_sha256": policy_sha256,
            "envelope_version": "phase8.1-formal-loco-evaluation-envelope-v1",
            "evaluation_summary_sha256": _file_sha256(summary_path),
            "experiment_id": EXPERIMENT_ID_V21,
            "fold_count": len(fold_evidence),
            "inventory_sha256": registry.inventory_sha256,
            "role_protocol_sha256": registry.role_protocol_sha256,
            "source_commit": args.source_commit,
            "status": "complete",
        }
        _write_json(staging / "evaluation_envelope.json", envelope)
        if len(fold_evidence) != 8:
            raise ValueError("formal_evaluation_incomplete")
        os.replace(staging, output)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        approval = require_canonical_d23_approval_v21(
            args.approval_record,
            role_protocol_path=args.role_protocol,
            analysis_policy_path=args.analysis_policy,
        )
        if args.fold != "all":
            raise ValueError("formal_evaluation_requires_exact_eight")
        return int(_run_authorized_loco(args=args, approval=approval))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
