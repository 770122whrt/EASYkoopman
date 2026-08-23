"""Contracts for exact-eight LOCO roles and dynamic opened-artifact audits."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.collection_v2 import (
    DatasetInventoryV2,
    EpisodeInventoryEntryV2,
    dataset_inventory_sha256_v2,
)
from koopman.evidence_v2 import canonical_sha256
from koopman.protocol_v2 import (
    MAIN_EXCITATION_FAMILIES,
    build_recommended_main_role_protocol_v1,
    main_role_intents_v2,
    validate_main_role_protocol_v1,
)
from koopman.splits_v2 import (
    ExpertLOCOViewV2,
    LOCOFoldManifestV2,
    PrimaryLOCOViewV2,
    build_loco_split_manifest_v2,
    load_primary_decision_view_v2,
    loco_split_sha256_v2,
    primary_view_for_fold_v2,
    expert_view_for_fold_v2,
    read_loco_split_manifest_v2,
    require_primary_view_v2,
    validate_loco_split_manifest_v2,
    validate_primary_access_audit_v2,
    write_loco_split_manifest_v2,
)


FROZEN_AT = "2026-08-24T00:00:00Z"
SPLIT_AT = "2026-08-24T00:01:00Z"


def _protocol() -> dict:
    return build_recommended_main_role_protocol_v1(frozen_at=FROZEN_AT)


def _inventory(protocol: dict | None = None) -> DatasetInventoryV2:
    role_protocol = _protocol() if protocol is None else protocol
    protocol_sha256 = canonical_sha256(role_protocol)
    entries = tuple(
        EpisodeInventoryEntryV2(
            configuration=intent.configuration,
            episode_id=intent.episode_id,
            role=intent.role,
            scenario=intent.scenario,
            seed=intent.seed,
            transition_count=intent.transition_count,
            transition_path=intent.transition_path,
            manifest_path=intent.manifest_path,
            transition_sha256=hashlib.sha256(
                f"transition:{intent.episode_id}".encode("utf-8")
            ).hexdigest(),
            manifest_sha256=hashlib.sha256(
                f"manifest:{intent.episode_id}".encode("utf-8")
            ).hexdigest(),
            transition_size_bytes=1,
            manifest_size_bytes=1,
            record_count=intent.transition_count,
            platform_context_sha256=hashlib.sha256(
                f"platform:{intent.configuration}".encode("utf-8")
            ).hexdigest(),
            evidence_level="local_contract",
        )
        for intent in main_role_intents_v2(role_protocol)
    )
    payload = {
        "entries": [entry.to_dict() for entry in entries],
        "envelope_sha256": None,
        "inventory_version": "phase8-dataset-inventory-v1",
        "qualification_level": "local_contract",
        "role_protocol_sha256": protocol_sha256,
        "runtime_sha256": hashlib.sha256(b"synthetic-runtime").hexdigest(),
        "source_commit": "1" * 40,
    }
    payload["inventory_sha256"] = dataset_inventory_sha256_v2(payload)
    return DatasetInventoryV2.from_dict(payload)


def _split():
    protocol = _protocol()
    inventory = _inventory(protocol)
    split = build_loco_split_manifest_v2(
        inventory, protocol, created_at=SPLIT_AT
    )
    return protocol, inventory, split


def test_recommended_main_protocol_is_exact_symmetric_pending_d23_proposal() -> None:
    protocol = _protocol()
    validate_main_role_protocol_v1(protocol)
    entries = protocol["entries"]

    assert protocol["protocol_version"] == "phase8-main-role-protocol-v1"
    assert protocol["approval_status"] == "pending_d23"
    assert protocol["proposal_only"] is True
    assert protocol["transition_count"] == 512
    assert len(entries) == 8 * 12
    assert {entry["configuration"] for entry in entries} == set(SUPPORTED_EMBODIMENTS)
    assert {entry["excitation_family"] for entry in entries} == set(
        MAIN_EXCITATION_FAMILIES
    )
    assert len({entry["episode_id"] for entry in entries}) == len(entries)
    assert len({entry["seed"] for entry in entries}) == len(entries)
    for configuration in SUPPORTED_EMBODIMENTS:
        selected = [entry for entry in entries if entry["configuration"] == configuration]
        assert [entry["role"] for entry in selected].count("fit") == 6
        assert [entry["role"] for entry in selected].count("validation") == 3
        assert [entry["role"] for entry in selected].count("test") == 3
        for role in ("fit", "validation", "test"):
            role_entries = [entry for entry in selected if entry["role"] == role]
            expected_repeats = 2 if role == "fit" else 1
            assert all(
                sum(
                    entry["excitation_family"] == family
                    for entry in role_entries
                )
                == expected_repeats
                for family in MAIN_EXCITATION_FAMILIES
            )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (lambda p: p["entries"][0].__setitem__("row_start", 0), "row_level_split_forbidden"),
        (
            lambda p: p["entries"][1].__setitem__(
                "episode_id", p["entries"][0]["episode_id"]
            ),
            "split_episode_overlap",
        ),
        (lambda p: p["entries"][0].__setitem__("role", "test"), "role_assignment_drift"),
        (lambda p: p["entries"].pop(), "configuration_matrix_mismatch"),
        (
            lambda p: p["entries"][0].__setitem__("configuration", "unknown"),
            "configuration_set_mismatch",
        ),
        (
            lambda p: p["entries"][0].__setitem__(
                "episode_id", "phase8-pilot-base-axis-pulse-s8101"
            ),
            "pilot_main_id_reuse",
        ),
        (lambda p: p["entries"].reverse(), "protocol_order_drift"),
    ),
)
def test_main_protocol_rejects_role_matrix_and_identity_mutations(
    mutation, reason: str
) -> None:
    protocol = deepcopy(_protocol())
    mutation(protocol)
    with pytest.raises(ValueError, match=reason):
        validate_main_role_protocol_v1(protocol)


def test_exact_eight_folds_use_complementary_seven_and_whole_episode_roles() -> None:
    protocol, inventory, split = _split()
    result = validate_loco_split_manifest_v2(split, inventory, protocol)

    assert result["fold_count"] == 8
    assert isinstance(split.folds, tuple)
    assert [fold.holdout_configuration for fold in split.folds] == list(
        SUPPORTED_EMBODIMENTS
    )
    for fold in split.folds:
        assert isinstance(fold, LOCOFoldManifestV2)
        assert len(fold.source_configurations) == 7
        assert set(fold.source_configurations) == set(SUPPORTED_EMBODIMENTS) - {
            fold.holdout_configuration
        }
        assert len(fold.primary_source_episode_ids) == 7 * 9
        assert len(fold.primary_heldout_test_episode_ids) == 3
        assert len(fold.expert_fit_validation_episode_ids) == 9
        assert len(fold.expert_test_episode_ids) == 3
        entries = {entry.episode_id: entry for entry in inventory.entries}
        assert {
            entries[episode_id].configuration
            for episode_id in fold.primary_source_episode_ids
        } == set(fold.source_configurations)
        assert {
            entries[episode_id].role for episode_id in fold.primary_source_episode_ids
        } == {"fit", "validation"}
        assert {
            entries[episode_id].configuration
            for episode_id in fold.primary_heldout_test_episode_ids
        } == {fold.holdout_configuration}
        assert {
            entries[episode_id].role
            for episode_id in fold.primary_heldout_test_episode_ids
        } == {"test"}
        assert not set(fold.primary_source_episode_ids) & set(
            fold.expert_fit_validation_episode_ids
        )


def test_primary_and_expert_namespaces_are_distinct_and_nonconvertible() -> None:
    protocol, inventory, split = _split()
    fold = split.folds[0]
    primary = primary_view_for_fold_v2(fold, inventory, protocol)
    expert = expert_view_for_fold_v2(fold, inventory, protocol)

    assert isinstance(primary, PrimaryLOCOViewV2)
    assert primary.selection_eligible is True
    assert isinstance(expert, ExpertLOCOViewV2)
    assert expert.selection_eligible is False
    assert not hasattr(expert, "as_primary")
    entries = {entry.episode_id: entry for entry in inventory.entries}
    assert {
        entries[episode_id].configuration for episode_id in expert.decision_episode_ids
    } == {fold.holdout_configuration}
    assert {
        entries[episode_id].role for episode_id in expert.decision_episode_ids
    } == {"fit", "validation"}
    with pytest.raises(ValueError, match="expert_promotion_forbidden"):
        require_primary_view_v2(expert)


def test_dynamic_loader_opens_only_exact_source_bytes_and_records_hashes() -> None:
    protocol, inventory, split = _split()
    fold = split.folds[3]
    primary = primary_view_for_fold_v2(fold, inventory, protocol)
    opened: list[tuple[str, str, str]] = []

    def opener(entry: EpisodeInventoryEntryV2) -> str:
        opened.append(
            (entry.episode_id, entry.configuration, entry.transition_sha256)
        )
        return entry.episode_id

    loaded, audit = load_primary_decision_view_v2(primary, inventory, opener)
    assert tuple(loaded) == primary.decision_episode_ids
    assert len(opened) == 7 * 9
    assert {configuration for _, configuration, _ in opened} == set(
        fold.source_configurations
    )
    assert fold.holdout_configuration not in {
        configuration for _, configuration, _ in opened
    }
    assert tuple(item.transition_sha256 for item in audit.opened_artifacts) == tuple(
        transition_hash for _, _, transition_hash in opened
    )
    assert validate_primary_access_audit_v2(fold, audit)["opened_count"] == 7 * 9


def test_forged_source_id_fails_before_any_heldout_byte_is_opened() -> None:
    protocol, inventory, split = _split()
    fold = split.folds[0]
    forged_ids = list(fold.primary_source_episode_ids)
    forged_ids[0] = fold.expert_fit_validation_episode_ids[0]
    forged = replace(fold, primary_source_episode_ids=tuple(forged_ids))
    opened: list[str] = []

    with pytest.raises(ValueError, match="heldout_design_leakage|fold_manifest_drift"):
        primary_view_for_fold_v2(forged, inventory, protocol)
    assert opened == []


def test_inventory_protocol_order_hash_and_timestamp_drift_fail_closed() -> None:
    protocol, inventory, split = _split()

    payload = inventory.to_dict()
    payload["entries"][0], payload["entries"][1] = (
        payload["entries"][1],
        payload["entries"][0],
    )
    payload["inventory_sha256"] = dataset_inventory_sha256_v2(payload)
    reordered = DatasetInventoryV2.from_dict(payload)
    with pytest.raises(ValueError, match="inventory_protocol_order_drift"):
        build_loco_split_manifest_v2(reordered, protocol, created_at=SPLIT_AT)

    mismatched_hash = replace(inventory, role_protocol_sha256="0" * 64)
    with pytest.raises(ValueError, match="role_protocol_hash_mismatch"):
        build_loco_split_manifest_v2(mismatched_hash, protocol, created_at=SPLIT_AT)

    with pytest.raises(ValueError, match="timestamp_order_invalid"):
        build_loco_split_manifest_v2(
            inventory, protocol, created_at="2026-08-23T23:59:59Z"
        )

    payload = split.to_dict()
    payload["inventory_sha256"] = "0" * 64
    payload["split_sha256"] = loco_split_sha256_v2(payload)
    with pytest.raises(ValueError, match="inventory_hash_mismatch"):
        validate_loco_split_manifest_v2(
            split.from_dict(payload), inventory, protocol
        )


def test_split_manifest_fresh_write_roundtrip_is_atomic(tmp_path: Path) -> None:
    protocol, inventory, split = _split()
    output = tmp_path / "loco_split_manifest.json"
    write_loco_split_manifest_v2(split, output)
    assert output.is_file()
    assert not output.with_name(f"{output.name}.part").exists()
    loaded = read_loco_split_manifest_v2(output, inventory, protocol)
    assert loaded == split

    with pytest.raises(ValueError, match="artifact_exists"):
        write_loco_split_manifest_v2(split, output)
    assert not output.with_name(f"{output.name}.part").exists()
