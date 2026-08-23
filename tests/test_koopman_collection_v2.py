"""Contracts for immutable Phase 8 multi-episode inventory and collections."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from koopman.collection_v2 import (
    DatasetInventoryV2,
    KoopmanDatasetCollectionV2,
    build_dataset_inventory_v2,
    dataset_inventory_sha256_v2,
    load_dataset_inventory_v2,
    load_episode_role_intents_v2,
    load_koopman_collection_v2,
    require_main_dataset_qualification_v2,
    validate_dataset_inventory_v2,
    write_dataset_inventory_v2,
)
from koopman.schema_v2 import validate_episode_artifact_v2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "koopman_phase8_multi_episode"
INTENT_PATH = FIXTURE_ROOT / "role_intent.json"
PILOT_ENVELOPE_PATH = (
    PROJECT_ROOT / "source" / "results" / "koopman_phase8_pilot" / "pilot_envelope.json"
)
EXPECTED_FIXTURE_TREE_SHA256 = (
    "9122d6646759ca359da056b52d1cc322f466d07f2ae26bfcbcb66557c7c97826"
)
LOCAL_RUNTIME_SHA256 = hashlib.sha256(b"phase8-local-runtime-v1\n").hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\n")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _intents():
    return load_episode_role_intents_v2(INTENT_PATH)


def _inventory(root: Path = FIXTURE_ROOT):
    return build_dataset_inventory_v2(
        root,
        _intents() if root == FIXTURE_ROOT else load_episode_role_intents_v2(root / "role_intent.json"),
        role_protocol_sha256=hashlib.sha256((root / "role_intent.json").read_bytes()).hexdigest(),
        runtime_sha256=LOCAL_RUNTIME_SHA256,
        envelope_sha256=None,
        qualification_level="local_contract",
    )


def test_committed_multi_episode_fixture_is_locked_local_contract() -> None:
    assert _tree_sha256(FIXTURE_ROOT) == EXPECTED_FIXTURE_TREE_SHA256
    intents = _intents()
    assert len(intents) == 9
    assert {intent.configuration for intent in intents} == {"base", "uuv6", "uuv4"}
    assert {intent.role for intent in intents} == {"fit", "validation", "test"}
    assert len({intent.episode_id for intent in intents}) == 9

    for intent in intents:
        result = validate_episode_artifact_v2(
            FIXTURE_ROOT / intent.transition_path,
            FIXTURE_ROOT / intent.manifest_path,
        )
        manifest = json.loads(
            (FIXTURE_ROOT / intent.manifest_path).read_text(encoding="utf-8")
        )
        assert result["configuration"] == intent.configuration
        assert result["episode_id"] == intent.episode_id
        assert result["record_count"] == intent.transition_count == 2
        assert result["evidence_level"] == "local_contract"
        assert manifest["transition_sha256"] == hashlib.sha256(
            (FIXTURE_ROOT / intent.transition_path).read_bytes()
        ).hexdigest()


def test_collection_preserves_episode_boundaries_indexes_and_exact_hashes() -> None:
    intents = _intents()
    inventory = _inventory()
    collection = load_koopman_collection_v2(FIXTURE_ROOT, inventory, intents=intents)

    assert isinstance(inventory, DatasetInventoryV2)
    assert isinstance(collection, KoopmanDatasetCollectionV2)
    assert isinstance(collection.episodes, tuple)
    assert collection.episode_ids == tuple(intent.episode_id for intent in intents)
    assert set(collection.by_configuration) == {"base", "uuv6", "uuv4"}
    assert set(collection.by_role) == {"fit", "validation", "test"}
    assert all(len(ids) == 3 for ids in collection.by_configuration.values())
    assert all(len(ids) == 3 for ids in collection.by_role.values())
    assert tuple(entry.transition_sha256 for entry in inventory.entries) == tuple(
        episode.transition_sha256 for episode in collection.episodes
    )
    with pytest.raises(TypeError):
        collection.by_role["fit"] = ()
    with pytest.raises(TypeError):
        collection.episodes[0].dataset.platform_contexts[0]["mass_kg"] = 0.0

    selected = collection.select_episodes(configurations={"base"}, roles={"fit", "test"})
    assert [episode.role for episode in selected] == ["fit", "test"]
    row_view = collection.row_view(configurations={"base"})
    assert row_view.X.shape == (6, 11)
    assert row_view.U.shape == (6, 4)
    assert row_view.X.flags.writeable is False
    assert [boundary.stop - boundary.start for boundary in row_view.boundaries] == [2, 2, 2]
    assert tuple(boundary.episode_id for boundary in row_view.boundaries) == tuple(
        episode.episode_id
        for episode in collection.select_episodes(configurations={"base"})
    )


def test_inventory_binds_postcollection_facts_to_precollection_role_intent() -> None:
    intents = _intents()
    inventory = _inventory()
    assert inventory.inventory_version == "phase8-dataset-inventory-v1"
    assert inventory.qualification_level == "local_contract"
    assert inventory.role_protocol_sha256 == hashlib.sha256(INTENT_PATH.read_bytes()).hexdigest()
    assert inventory.runtime_sha256 == LOCAL_RUNTIME_SHA256
    assert inventory.envelope_sha256 is None
    assert inventory.inventory_sha256 == dataset_inventory_sha256_v2(inventory.to_dict())
    assert validate_dataset_inventory_v2(
        inventory, root=FIXTURE_ROOT, intents=intents
    )["episode_count"] == 9

    mutated = list(intents)
    mutated[0] = replace(mutated[0], role="test")
    with pytest.raises(ValueError, match="role_assignment_drift"):
        validate_dataset_inventory_v2(inventory, root=FIXTURE_ROOT, intents=mutated)
    with pytest.raises(ValueError, match="duplicate_episode_id"):
        build_dataset_inventory_v2(
            FIXTURE_ROOT,
            intents + (intents[0],),
            role_protocol_sha256=hashlib.sha256(INTENT_PATH.read_bytes()).hexdigest(),
            runtime_sha256=LOCAL_RUNTIME_SHA256,
            envelope_sha256=None,
            qualification_level="local_contract",
        )


@pytest.mark.parametrize("mutation", ("missing", "extra", "stale_manifest"))
def test_inventory_rejects_missing_extra_and_stale_files(tmp_path: Path, mutation: str) -> None:
    root = tmp_path / "collection"
    shutil.copytree(FIXTURE_ROOT, root)
    intents = load_episode_role_intents_v2(root / "role_intent.json")
    if mutation == "missing":
        (root / intents[0].transition_path).unlink()
    elif mutation == "extra":
        shutil.copyfile(
            root / intents[0].transition_path,
            root / "episodes" / "stale-extra.jsonl",
        )
    else:
        shutil.copyfile(
            root / intents[0].manifest_path,
            root / "manifests" / "stale-extra.manifest.json",
        )

    with pytest.raises(ValueError, match="inventory_set_mismatch"):
        _inventory(root)


def test_inventory_revalidates_hash_count_and_episode_invariants(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    shutil.copytree(FIXTURE_ROOT, root)
    intents = load_episode_role_intents_v2(root / "role_intent.json")
    inventory = _inventory(root)
    output = root / "dataset_inventory.json"
    write_dataset_inventory_v2(inventory, output)

    transition = root / intents[0].transition_path
    transition.write_bytes(transition.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="artifact_hash_mismatch"):
        load_dataset_inventory_v2(output, root=root, intents=intents)

    root = tmp_path / "collection-count"
    shutil.copytree(FIXTURE_ROOT, root)
    intents = load_episode_role_intents_v2(root / "role_intent.json")
    inventory = _inventory(root)
    payload = inventory.to_dict()
    payload["entries"][0]["record_count"] += 1
    payload["inventory_sha256"] = dataset_inventory_sha256_v2(payload)
    mutated = DatasetInventoryV2.from_dict(payload)
    with pytest.raises(ValueError, match="inventory_invariant_mismatch"):
        validate_dataset_inventory_v2(mutated, root=root, intents=intents)

    payload = inventory.to_dict()
    payload["entries"][0]["scenario"] = "postcollection-role-edit"
    payload["inventory_sha256"] = dataset_inventory_sha256_v2(payload)
    mutated = DatasetInventoryV2.from_dict(payload)
    with pytest.raises(ValueError, match="role_assignment_drift"):
        validate_dataset_inventory_v2(mutated, root=root, intents=intents)


def test_inventory_cannot_precede_episode_bytes_and_is_bounded(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    shutil.copyfile(INTENT_PATH, root / "role_intent.json")
    intents = load_episode_role_intents_v2(root / "role_intent.json")
    with pytest.raises(ValueError, match="inventory_set_mismatch"):
        build_dataset_inventory_v2(
            root,
            intents,
            role_protocol_sha256=hashlib.sha256((root / "role_intent.json").read_bytes()).hexdigest(),
            runtime_sha256=LOCAL_RUNTIME_SHA256,
            envelope_sha256=None,
            qualification_level="local_contract",
        )
    with pytest.raises(ValueError, match="inventory_too_large"):
        build_dataset_inventory_v2(
            FIXTURE_ROOT,
            _intents(),
            role_protocol_sha256=hashlib.sha256(INTENT_PATH.read_bytes()).hexdigest(),
            runtime_sha256=LOCAL_RUNTIME_SHA256,
            envelope_sha256=None,
            qualification_level="local_contract",
            max_entries=8,
        )


def test_inventory_accepts_a_confined_relative_collection_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    relative_root = FIXTURE_ROOT.relative_to(PROJECT_ROOT)
    intents = _intents()
    inventory = build_dataset_inventory_v2(
        relative_root,
        intents,
        role_protocol_sha256=hashlib.sha256(INTENT_PATH.read_bytes()).hexdigest(),
        runtime_sha256=LOCAL_RUNTIME_SHA256,
        envelope_sha256=None,
        qualification_level="local_contract",
    )
    assert inventory.inventory_sha256


def test_inventory_rejects_escape_and_symlinked_episode_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intents = list(_intents())
    with pytest.raises(ValueError, match="reference_path_invalid"):
        intents[0] = replace(intents[0], transition_path="../escape.jsonl")
        build_dataset_inventory_v2(
            FIXTURE_ROOT,
            intents,
            role_protocol_sha256=hashlib.sha256(INTENT_PATH.read_bytes()).hexdigest(),
            runtime_sha256=LOCAL_RUNTIME_SHA256,
            envelope_sha256=None,
            qualification_level="local_contract",
        )

    root = tmp_path / "collection"
    shutil.copytree(FIXTURE_ROOT, root)
    intents = list(load_episode_role_intents_v2(root / "role_intent.json"))
    target = root / intents[0].transition_path
    outside = tmp_path / "outside.jsonl"
    shutil.copyfile(target, outside)
    probe = tmp_path / "symlink-probe.jsonl"
    try:
        probe.symlink_to(outside)
        probe.unlink()
        target.unlink()
        target.symlink_to(outside)
    except OSError:
        original_is_symlink = Path.is_symlink

        def _is_symlink(path: Path) -> bool:
            return path.absolute() == target.absolute() or original_is_symlink(path)

        monkeypatch.setattr(Path, "is_symlink", _is_symlink)
    with pytest.raises(ValueError, match="artifact_not_regular_file"):
        build_dataset_inventory_v2(
            root,
            intents,
            role_protocol_sha256=hashlib.sha256((root / "role_intent.json").read_bytes()).hexdigest(),
            runtime_sha256=LOCAL_RUNTIME_SHA256,
            envelope_sha256=None,
            qualification_level="local_contract",
        )


def test_smoke_pilot_and_local_fixtures_cannot_qualify_as_main_dataset() -> None:
    pilot = json.loads(PILOT_ENVELOPE_PATH.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="evidence_level_mismatch"):
        require_main_dataset_qualification_v2(
            artifact_origin_level="server_isaac_smoke",
            qualification_level="server_isaac_smoke",
        )
    with pytest.raises(ValueError, match="evidence_level_mismatch"):
        require_main_dataset_qualification_v2(
            artifact_origin_level=pilot["artifact_origin_level"],
            qualification_level=pilot["qualification_level"],
        )
    with pytest.raises(ValueError, match="evidence_level_mismatch"):
        require_main_dataset_qualification_v2(
            artifact_origin_level="local_contract",
            qualification_level=_inventory().qualification_level,
        )


def test_inventory_cli_atomically_writes_only_a_fresh_target(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    shutil.copytree(FIXTURE_ROOT, root)
    output = root / "dataset_inventory.json"
    command = [
        sys.executable,
        "workflows/build_koopman_v2_inventory.py",
        "--root",
        str(root),
        "--intent",
        str(root / "role_intent.json"),
        "--runtime-sha256",
        LOCAL_RUNTIME_SHA256,
        "--output",
        str(output),
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert not output.with_name(f"{output.name}.part").exists()
    loaded = load_dataset_inventory_v2(
        output,
        root=root,
        intents=load_episode_role_intents_v2(root / "role_intent.json"),
    )
    assert loaded.inventory_sha256 == json.loads(result.stdout)["inventory_sha256"]

    repeated = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert repeated.returncode != 0
    assert "artifact_exists" in repeated.stderr
    assert not output.with_name(f"{output.name}.part").exists()
